'use client';

import { useState, useMemo, useCallback } from 'react';
import { useDroppable, useDraggable } from '@dnd-kit/core';
import {
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Folder,
  FolderOpen,
  GripVertical,
  Plus,
  Pencil,
  Trash2,
  MoreHorizontal,
  Shield,
  Search,
  X,
} from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollAreaZag } from '@/components/ui/scroll-area-zag';
import { cn } from '@/lib/utils';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import {
  useCreateDirectory,
  useUpdateDirectory,
  useDeleteDirectory,
  useDirectoryTree,
} from '../../attachments/hooks/useAttachments';
import { useQuickAccess, useAddQuickAccess, useRemoveQuickAccess } from '@/hooks/useQuickAccess';
import { Star, StarOff } from 'lucide-react';

interface DirectoryTreeSidebarProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** When set, folder menu includes adjusting access levels for all attachments in the folder subtree. */
  onAdjustFolderAccessLevels?: (directoryId: string) => void;
}

const FOLDER_DROP_PREFIX = 'folder-';
const FOLDER_ALL_ID = 'folder-all';

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

function AllAttachmentsDropTarget({
  isSelected,
  onSelect,
}: {
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: FOLDER_ALL_ID,
    data: { type: 'folder', directoryId: null },
  });
  return (
    <button
      ref={setNodeRef}
      type="button"
      className={cn(
        'w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left',
        isSelected && 'bg-primary text-primary-foreground font-medium',
        isOver && 'ring-2 ring-primary ring-inset'
      )}
      onClick={onSelect}
    >
      <Folder className={cn('size-4 shrink-0', isSelected ? 'text-primary-foreground' : 'text-muted-foreground')} />
      All attachments
    </button>
  );
}

function filterTreeBySearch(
  nodes: AttachmentDirectoryTreeNode[],
  query: string
): { filtered: AttachmentDirectoryTreeNode[]; matchedAncestors: Set<string> } {
  const q = query.trim().toLowerCase();
  const matchedAncestors = new Set<string>();
  if (!q) return { filtered: nodes, matchedAncestors };

  const visit = (node: AttachmentDirectoryTreeNode): AttachmentDirectoryTreeNode | null => {
    const selfMatch = node.name.toLowerCase().includes(q);
    const filteredChildren = (node.children ?? [])
      .map(visit)
      .filter((n): n is AttachmentDirectoryTreeNode => n !== null);
    if (selfMatch || filteredChildren.length > 0) {
      if (filteredChildren.length > 0) matchedAncestors.add(node.id);
      return { ...node, children: filteredChildren };
    }
    return null;
  };

  const filtered = nodes.map(visit).filter((n): n is AttachmentDirectoryTreeNode => n !== null);
  return { filtered, matchedAncestors };
}

function findPathToFolder(
  nodes: AttachmentDirectoryTreeNode[],
  targetId: string,
  path: string[] = []
): string[] | null {
  for (const node of nodes) {
    const currentPath = [...path, node.id];
    if (node.id === targetId) return currentPath;
    if (node.children) {
      const found = findPathToFolder(node.children, targetId, currentPath);
      if (found) return found;
    }
  }
  return null;
}

const ATTACHMENT_DIRECTORIES_PATH = '/resource-management/attachment-directories';

function DirectoryRow({
  node,
  depth,
  selectedId,
  expandedIds,
  onSelect,
  onCreateSubfolder,
  onRename,
  onDelete,
  onToggleExpand,
  quickAccessEntryIdByDirectoryId,
  onPinToQuickAccess,
  onUnpinFromQuickAccess,
  onAdjustFolderAccessLevels,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  onSelect: (id: string | null) => void;
  onCreateSubfolder: (parentId: string) => void;
  onRename: (id: string, currentName: string) => void;
  onDelete: (id: string, name: string) => void;
  onToggleExpand: (id: string) => void;
  quickAccessEntryIdByDirectoryId: Record<string, string>;
  onPinToQuickAccess: (directoryId: string, label: string) => void;
  onUnpinFromQuickAccess: (entryId: string) => void;
  onAdjustFolderAccessLevels?: (directoryId: string) => void;
}) {
  const isExpanded = expandedIds.has(node.id);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedId === node.id;

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `${FOLDER_DROP_PREFIX}${node.id}`,
    data: { type: 'folder', directoryId: node.id },
  });

  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: `${FOLDER_DROP_PREFIX}${node.id}`,
    data: { type: 'folder', directoryId: node.id, folderName: node.name },
  });

  return (
    <div className="flex flex-col">
      <div
        ref={setDropRef}
        className={cn(
          'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer min-w-0',
          isSelected && 'bg-primary text-primary-foreground font-medium',
          isOver && 'ring-2 ring-primary ring-inset',
          isDragging && 'opacity-50'
        )}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.id)}
      >
        <span
          ref={setDragRef}
          className={cn(
            'touch-none p-0.5 rounded shrink-0 cursor-grab active:cursor-grabbing',
            isSelected ? 'hover:bg-primary-foreground/20' : 'hover:bg-muted'
          )}
          title="Drag to move folder"
          {...listeners}
          {...attributes}
          onClick={(e) => e.stopPropagation()}
        >
          <GripVertical className={cn('size-4', isSelected ? 'text-primary-foreground' : 'text-muted-foreground')} />
        </span>
        <button
          type="button"
          className={cn(
            'p-0.5 rounded shrink-0',
            isSelected ? 'hover:bg-primary-foreground/20' : 'hover:bg-muted'
          )}
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand(node.id);
          }}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          <ChevronRight
            className={cn(
              'size-4 transition-transform',
              isSelected ? 'text-primary-foreground' : 'text-muted-foreground',
              isExpanded && 'rotate-90'
            )}
          />
        </button>
        {hasChildren && isExpanded ? (
          <FolderOpen className={cn('size-4 shrink-0', isSelected ? 'text-primary-foreground' : 'text-muted-foreground')} />
        ) : (
          <Folder className={cn('size-4 shrink-0', isSelected ? 'text-primary-foreground' : 'text-muted-foreground')} />
        )}
        <span className="whitespace-nowrap" title={node.name}>{node.name}</span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 opacity-0 group-hover:opacity-100"
              aria-label="Folder actions"
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {quickAccessEntryIdByDirectoryId[node.id] ? (
              <DropdownMenuItem
                onClick={() => onUnpinFromQuickAccess(quickAccessEntryIdByDirectoryId[node.id])}
              >
                <StarOff className="size-4 mr-2" />
                Unpin from Quick Access
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={() => onPinToQuickAccess(node.id, node.name)}>
                <Star className="size-4 mr-2" />
                Pin to Quick Access
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => onCreateSubfolder(node.id)}>
              <Plus className="size-4 mr-2" />
              Add subfolder
            </DropdownMenuItem>
            {onAdjustFolderAccessLevels ? (
              <DropdownMenuItem onClick={() => onAdjustFolderAccessLevels(node.id)}>
                <Shield className="size-4 mr-2" />
                Adjust access levels
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem onClick={() => onRename(node.id, node.name)}>
              <Pencil className="size-4 mr-2" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onDelete(node.id, node.name)}
            >
              <Trash2 className="size-4 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <DirectoryRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expandedIds={expandedIds}
              onSelect={onSelect}
              onCreateSubfolder={onCreateSubfolder}
              onRename={onRename}
              onDelete={onDelete}
              onToggleExpand={onToggleExpand}
              quickAccessEntryIdByDirectoryId={quickAccessEntryIdByDirectoryId}
              onPinToQuickAccess={onPinToQuickAccess}
              onUnpinFromQuickAccess={onUnpinFromQuickAccess}
              onAdjustFolderAccessLevels={onAdjustFolderAccessLevels}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function buildFolderQuickAccessPath(directoryId: string): string {
  return `${ATTACHMENT_DIRECTORIES_PATH}?directoryId=${directoryId}`;
}

export default function DirectoryTreeSidebar({
  selectedId,
  onSelect,
  onAdjustFolderAccessLevels,
}: DirectoryTreeSidebarProps) {
  const { data: tree = [], isLoading } = useDirectoryTree();
  const createMutation = useCreateDirectory();
  const updateMutation = useUpdateDirectory();
  const deleteMutation = useDeleteDirectory();
  const { data: quickAccessList = [] } = useQuickAccess();
  const addQuickAccessMutation = useAddQuickAccess();
  const removeQuickAccessMutation = useRemoveQuickAccess();

  const quickAccessEntryIdByDirectoryId = useMemo(() => {
    const map: Record<string, string> = {};
    for (const item of quickAccessList) {
      const match = item.path.match(/\?directoryId=([^&]+)/);
      if (match) map[match[1]] = item.id;
    }
    return map;
  }, [quickAccessList]);

  const onPinToQuickAccess = useCallback(
    (directoryId: string, label: string) => {
      addQuickAccessMutation.mutate({
        path: buildFolderQuickAccessPath(directoryId),
        label,
      });
    },
    [addQuickAccessMutation]
  );

  const onUnpinFromQuickAccess = useCallback(
    (entryId: string) => {
      removeQuickAccessMutation.mutate(entryId);
    },
    [removeQuickAccessMutation]
  );

  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [addParentId, setAddParentId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState('');

  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameName, setRenameName] = useState('');

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const { filtered: filteredTree, matchedAncestors } = useMemo(
    () => filterTreeBySearch(tree, searchQuery),
    [tree, searchQuery]
  );

  const pathToSelected = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const path = findPathToFolder(tree, selectedId);
    if (!path) return new Set<string>();
    const ids = new Set<string>();
    for (let i = 0; i < path.length - 1; i++) ids.add(path[i]);
    return ids;
  }, [tree, selectedId]);

  const allFolderIds = useMemo(() => collectAllFolderIds(tree), [tree]);

  const subtreeFolderIds = useMemo(() => {
    if (!selectedId) return null;
    const node = findNodeById(tree, selectedId);
    return node ? collectSubtreeFolderIds(node) : null;
  }, [tree, selectedId]);

  const [expandedIdsState, setExpandedIdsState] = useState<Set<string>>(new Set());
  const expandedIds = useMemo(() => {
    const merged = new Set(expandedIdsState);
    pathToSelected.forEach((id) => merged.add(id));
    if (searchQuery.trim()) matchedAncestors.forEach((id) => merged.add(id));
    return merged;
  }, [expandedIdsState, pathToSelected, matchedAncestors, searchQuery]);

  const handleExpandAll = useCallback(() => {
    const idsToExpand = subtreeFolderIds ?? allFolderIds;
    setExpandedIdsState((prev) => {
      const next = new Set(prev);
      idsToExpand.forEach((id) => next.add(id));
      return next;
    });
  }, [subtreeFolderIds, allFolderIds]);

  const handleCollapseAll = useCallback(() => {
    const idsToCollapse = subtreeFolderIds ?? allFolderIds;
    setExpandedIdsState((prev) => {
      const next = new Set(prev);
      idsToCollapse.forEach((id) => next.delete(id));
      return next;
    });
  }, [subtreeFolderIds, allFolderIds]);

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIdsState((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const openAddDialog = (parentId: string | null) => {
    setAddParentId(parentId);
    setNewFolderName('');
    setAddDialogOpen(true);
  };

  const openRenameDialog = (id: string, currentName: string) => {
    setRenameId(id);
    setRenameName(currentName);
    setRenameDialogOpen(true);
  };

  const openDeleteDialog = (id: string, name: string) => {
    setDeleteTarget({ id, name });
    setDeleteDialogOpen(true);
  };

  const handleCreate = () => {
    if (!newFolderName.trim()) return;
    createMutation.mutate(
      { name: newFolderName.trim(), parentId: addParentId ?? undefined },
      { onSuccess: () => setAddDialogOpen(false) }
    );
  };

  const handleRename = () => {
    if (!renameId || !renameName.trim()) return;
    updateMutation.mutate(
      { id: renameId, data: { name: renameName.trim() } },
      { onSuccess: () => setRenameDialogOpen(false) }
    );
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        setDeleteDialogOpen(false);
        setDeleteTarget(null);
        if (selectedId === deleteTarget.id) onSelect(null);
      },
    });
  };

  return (
    <>
      <div className="flex h-full w-full min-w-0 flex-col border-r bg-muted/30">
        <div className="flex items-center justify-between gap-1 p-2 border-b">
          <span className="text-sm font-medium truncate">Folders</span>
          <div className="flex items-center gap-0.5 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              className="size-8 p-0"
              title={selectedId ? 'Expand all in selected folder' : 'Expand all'}
              onClick={handleExpandAll}
            >
              <ChevronDown className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="size-8 p-0"
              title={selectedId ? 'Collapse all in selected folder' : 'Collapse all'}
              onClick={handleCollapseAll}
            >
              <ChevronUp className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => openAddDialog(null)}
              data-guide-target="resource-management.files.add-folder-button"
            >
              <Plus className="size-4 mr-1" />
              Add
            </Button>
          </div>
        </div>
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
            <Input
              type="text"
              placeholder="Search folders..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-8 h-8 text-sm"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-muted"
                aria-label="Clear search"
              >
                <X className="size-3.5 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
        <ScrollAreaZag className="flex-1">
          <div className="min-w-max p-1 py-2">
            {!searchQuery && (
              <AllAttachmentsDropTarget
                isSelected={selectedId === null}
                onSelect={() => onSelect(null)}
              />
            )}
            {isLoading ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">Loading…</div>
            ) : filteredTree.length === 0 && searchQuery ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">No folders match &quot;{searchQuery}&quot;</div>
            ) : (
              filteredTree.map((node) => (
                <DirectoryRow
                  key={node.id}
                  node={node}
                  depth={0}
                  selectedId={selectedId}
                  expandedIds={expandedIds}
                  onSelect={onSelect}
                  onCreateSubfolder={(parentId) => {
                    setAddParentId(parentId);
                    setNewFolderName('');
                    setAddDialogOpen(true);
                  }}
                  onRename={openRenameDialog}
                  onDelete={openDeleteDialog}
                  onToggleExpand={handleToggleExpand}
                  quickAccessEntryIdByDirectoryId={quickAccessEntryIdByDirectoryId}
                  onPinToQuickAccess={onPinToQuickAccess}
                  onUnpinFromQuickAccess={onUnpinFromQuickAccess}
                  onAdjustFolderAccessLevels={onAdjustFolderAccessLevels}
                />
              ))
            )}
          </div>
        </ScrollAreaZag>
      </div>

      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{addParentId ? 'New subfolder' : 'New folder'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="new-folder-name">Name</Label>
            <Input
              id="new-folder-name"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Folder name"
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!newFolderName.trim() || createMutation.isPending}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename folder</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rename-folder-name">Name</Label>
            <Input
              id="rename-folder-name"
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
              placeholder="Folder name"
              onKeyDown={(e) => e.key === 'Enter' && handleRename()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRename} disabled={!renameName.trim() || updateMutation.isPending}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteDialogOpen} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete folder</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Move &quot;{deleteTarget?.name}&quot; to Trash? This folder and all subfolders will be moved to Trash.
            All attachments in this folder and its subfolders will be archived. You can restore them from the Trash page.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMutation.isPending}>
              Move to Trash
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
