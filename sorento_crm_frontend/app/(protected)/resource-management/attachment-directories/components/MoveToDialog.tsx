'use client';

import { useMemo, useState } from 'react';
import { ChevronRight, Folder, FolderOpen } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDirectoryTree } from '../../attachments/hooks/useAttachments';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';

export interface MoveSelection {
  fileIds: string[];
  folderIds: string[];
}

interface MoveToDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selection: MoveSelection;
  /** Resolved destination: null = drive root. */
  onMove: (destinationId: string | null) => void;
  isMoving?: boolean;
}

function collectDescendants(node: AttachmentDirectoryTreeNode, into: Set<string>) {
  into.add(node.id);
  node.children?.forEach((c) => collectDescendants(c, into));
}

/**
 * Universal non-drag move path (UAC E5 / mobile H3): pick a destination folder
 * from the tree and move the selected files/folders there. Folders being moved
 * (and their descendants) are disabled as targets so the FE never offers a
 * cycle (the backend also rejects cycles - E4).
 */
export default function MoveToDialog({
  open,
  onOpenChange,
  selection,
  onMove,
  isMoving = false,
}: MoveToDialogProps) {
  const { data: tree = [] } = useDirectoryTree();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState<string | null>(null);

  // Folders that cannot be a destination: the moved folders themselves + their
  // subtrees (cycle guard).
  const blocked = useMemo(() => {
    const set = new Set<string>();
    if (selection.folderIds.length === 0) return set;
    const movedSet = new Set(selection.folderIds);
    const walk = (nodes: AttachmentDirectoryTreeNode[]) => {
      for (const node of nodes) {
        if (movedSet.has(node.id)) collectDescendants(node, set);
        else if (node.children?.length) walk(node.children);
      }
    };
    walk(tree);
    return set;
  }, [tree, selection.folderIds]);

  const totalCount = selection.fileIds.length + selection.folderIds.length;

  const renderNode = (node: AttachmentDirectoryTreeNode, depth: number) => {
    const isExpanded = expanded.has(node.id);
    const hasChildren = (node.children?.length ?? 0) > 0;
    const isBlocked = blocked.has(node.id);
    const isSelected = target === node.id;
    return (
      <div key={node.id} className="flex flex-col">
        <div
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1.5 text-sm',
            isBlocked
              ? 'cursor-not-allowed opacity-40'
              : 'cursor-pointer hover:bg-muted',
            isSelected && 'bg-primary text-primary-foreground hover:bg-primary'
          )}
          style={{ paddingLeft: 8 + depth * 16 }}
          onClick={() => {
            if (!isBlocked) setTarget(node.id);
          }}
        >
          <button
            type="button"
            className={cn('p-0.5 rounded shrink-0', !hasChildren && 'invisible')}
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((prev) => {
                const next = new Set(prev);
                if (next.has(node.id)) next.delete(node.id);
                else next.add(node.id);
                return next;
              });
            }}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            <ChevronRight className={cn('size-4 transition-transform', isExpanded && 'rotate-90')} />
          </button>
          {hasChildren && isExpanded ? (
            <FolderOpen className="size-4 shrink-0" />
          ) : (
            <Folder className="size-4 shrink-0" />
          )}
          <span className="truncate" title={node.name}>
            {node.name}
          </span>
        </div>
        {hasChildren && isExpanded && (
          <div>{node.children!.map((child) => renderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            Move {totalCount} item{totalCount === 1 ? '' : 's'}
          </DialogTitle>
        </DialogHeader>
        <div className="max-h-[50vh] overflow-y-auto rounded-md border p-1">
          <div
            className={cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer hover:bg-muted',
              target === null && 'bg-primary text-primary-foreground hover:bg-primary'
            )}
            onClick={() => setTarget(null)}
          >
            <Folder className="size-4 shrink-0" />
            <span>All files (root)</span>
          </div>
          {tree.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">No folders yet.</p>
          ) : (
            tree.map((node) => renderNode(node, 0))
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isMoving}>
            Cancel
          </Button>
          <Button onClick={() => onMove(target)} disabled={isMoving}>
            {isMoving ? 'Moving…' : 'Move here'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
