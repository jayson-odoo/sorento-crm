'use client';

import { useState, useMemo, useEffect } from 'react';
import { useDroppable } from '@dnd-kit/core';
import {
  ChevronRight,
  Folder,
  FolderOpen,
  Plus,
  Pencil,
  Trash2,
  MoreHorizontal,
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

interface DirectoryTreeSidebarProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const FOLDER_DROP_PREFIX = 'folder-';
const FOLDER_ALL_ID = 'folder-all';

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
        isSelected && 'bg-accent text-accent-foreground',
        isOver && 'ring-2 ring-primary ring-inset'
      )}
      onClick={onSelect}
    >
      <Folder className="size-4 text-muted-foreground shrink-0" />
      All attachments
    </button>
  );
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

function DirectoryRow({
  node,
  depth,
  selectedId,
  onSelect,
  onCreateSubfolder,
  onRename,
  onDelete,
  expandedFolderIds,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onCreateSubfolder: (parentId: string) => void;
  onRename: (id: string, currentName: string) => void;
  onDelete: (id: string, name: string) => void;
  expandedFolderIds: Set<string>;
}) {
  const shouldBeExpanded = expandedFolderIds.has(node.id);
  const [expanded, setExpanded] = useState(shouldBeExpanded);

  useEffect(() => {
    if (shouldBeExpanded && !expanded) {
      setExpanded(true);
    }
  }, [shouldBeExpanded, expanded]);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedId === node.id;

  const { setNodeRef, isOver } = useDroppable({
    id: `${FOLDER_DROP_PREFIX}${node.id}`,
    data: { type: 'folder', directoryId: node.id },
  });

  return (
    <div className="flex flex-col">
      <div
        ref={setNodeRef}
        className={cn(
          'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer min-w-0',
          isSelected && 'bg-accent text-accent-foreground',
          isOver && 'ring-2 ring-primary ring-inset'
        )}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.id)}
      >
        <button
          type="button"
          className="p-0.5 hover:bg-muted rounded shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((x) => !x);
          }}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          <ChevronRight
            className={cn('size-4 text-muted-foreground transition-transform', expanded && 'rotate-90')}
          />
        </button>
        {hasChildren && expanded ? (
          <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <Folder className="size-4 shrink-0 text-muted-foreground" />
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
            <DropdownMenuItem onClick={() => onCreateSubfolder(node.id)}>
              <Plus className="size-4 mr-2" />
              Add subfolder
            </DropdownMenuItem>
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
      {hasChildren && expanded && (
        <div>
          {node.children!.map((child) => (
            <DirectoryRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              onCreateSubfolder={onCreateSubfolder}
              onRename={onRename}
              onDelete={onDelete}
              expandedFolderIds={expandedFolderIds}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DirectoryTreeSidebar({ selectedId, onSelect }: DirectoryTreeSidebarProps) {
  const { data: tree = [], isLoading } = useDirectoryTree();
  const createMutation = useCreateDirectory();
  const updateMutation = useUpdateDirectory();
  const deleteMutation = useDeleteDirectory();

  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [addParentId, setAddParentId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState('');

  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameName, setRenameName] = useState('');

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const expandedFolderIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const path = findPathToFolder(tree, selectedId);
    if (!path) return new Set<string>();
    const ids = new Set<string>();
    for (let i = 0; i < path.length - 1; i++) {
      ids.add(path[i]);
    }
    return ids;
  }, [tree, selectedId]);

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
        <div className="flex items-center justify-between p-2 border-b">
          <span className="text-sm font-medium">Folders</span>
          <Button variant="outline" size="sm" onClick={() => openAddDialog(null)}>
            <Plus className="size-4 mr-1" />
            Add
          </Button>
        </div>
        <ScrollAreaZag className="flex-1">
          <div className="min-w-max p-1 py-2">
            <AllAttachmentsDropTarget
              isSelected={!selectedId}
              onSelect={() => onSelect(null)}
            />
            {isLoading ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">Loading…</div>
            ) : (
              tree.map((node) => (
                <DirectoryRow
                  key={node.id}
                  node={node}
                  depth={0}
                  selectedId={selectedId}
                  onSelect={onSelect}
                  onCreateSubfolder={(parentId) => {
                    setAddParentId(parentId);
                    setNewFolderName('');
                    setAddDialogOpen(true);
                  }}
                  onRename={openRenameDialog}
                  onDelete={openDeleteDialog}
                  expandedFolderIds={expandedFolderIds}
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
            Delete &quot;{deleteTarget?.name}&quot;? This folder and all subfolders will be removed. All attachments
            in this folder and its subfolders will be deleted. This cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMutation.isPending}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
