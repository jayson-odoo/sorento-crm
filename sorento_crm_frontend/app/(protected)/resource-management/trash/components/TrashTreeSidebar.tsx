'use client';

import { useState, useCallback, useMemo } from 'react';
import { ChevronRight, ChevronDown, ChevronUp, Folder, FolderOpen, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollAreaZag } from '@/components/ui/scroll-area-zag';
import { cn } from '@/lib/utils';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import { useDirectoryTree, useRestoreDirectory } from '../../attachments/hooks/useAttachments';

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

function DeletedFolderRow({
  node,
  depth,
  selectedId,
  expandedIds,
  onSelect,
  onRestore,
  onToggleExpand,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  onSelect: (id: string) => void;
  onRestore: (id: string) => void;
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
        <Button
          variant="ghost"
          size="sm"
          className="size-7 shrink-0 opacity-0 group-hover:opacity-100"
          title="Restore folder and contents"
          onClick={(e) => {
            e.stopPropagation();
            onRestore(node.id);
          }}
        >
          <RotateCcw className="size-4" />
        </Button>
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
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const allFolderIds = useMemo(() => collectAllFolderIds(deletedTree), [deletedTree]);

  const handleExpandAll = useCallback(() => {
    setExpandedIds(new Set(allFolderIds));
  }, [allFolderIds]);

  const handleCollapseAll = useCallback(() => {
    setExpandedIds(new Set());
  }, []);

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  return (
    <div className="flex h-full w-full min-w-0 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between gap-1 p-2 border-b">
        <span className="text-sm font-medium truncate">Deleted folders</span>
        <div className="flex items-center gap-0.5 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            title="Expand all"
            onClick={handleExpandAll}
          >
            <ChevronDown className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            title="Collapse all"
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
                onToggleExpand={handleToggleExpand}
              />
            ))
          )}
        </div>
      </ScrollAreaZag>
    </div>
  );
}
