'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronRight, ChevronDown, ChevronUp, Folder, FolderOpen, FileText, LoaderCircleIcon, X, Search } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getDirectoryTree } from '@/app/(protected)/resource-management/attachments/services/directoryService';
import { getAttachments } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import type { AttachmentDirectoryTreeNode } from '@/app/(protected)/resource-management/attachments/services/directoryService';
import type { Attachment } from '@/app/(protected)/resource-management/attachments/types/attachment.types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

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

function ReadOnlyFolderTree({
  selectedId,
  onSelect,
  tree,
  expanded,
  onToggleExpand,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  tree: AttachmentDirectoryTreeNode[];
  expanded: Set<string>;
  onToggleExpand: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-0.5 py-1">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={cn(
          'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left w-full',
          selectedId === null && 'bg-accent text-accent-foreground'
        )}
      >
        <Folder className="size-4 text-muted-foreground shrink-0" />
        All attachments
      </button>
      {tree.map((node) => (
        <FolderNode
          key={node.id}
          node={node}
          depth={0}
          selectedId={selectedId}
          expanded={expanded}
          onToggleExpand={onToggleExpand}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function FolderNode({
  node,
  depth,
  selectedId,
  expanded,
  onToggleExpand,
  onSelect,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  expanded: Set<string>;
  onToggleExpand: (id: string) => void;
  onSelect: (id: string | null) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expanded.has(node.id);
  const isSelected = selectedId === node.id;

  return (
    <div className="flex flex-col">
      <div
        className={cn(
          'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer min-w-0',
          isSelected && 'bg-accent text-accent-foreground'
        )}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.id)}
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
        <span className="truncate" title={node.name}>{node.name}</span>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <FolderNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expanded={expanded}
              onToggleExpand={onToggleExpand}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export interface ComplaintLinkAttachmentBrowserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityId: string;
  /** Attachment IDs already linked to this entity (so we can exclude them from the list). */
  linkedAttachmentIds: Set<string>;
  /** API call to link one attachment ID to the entity. */
  linkAttachment: (entityId: string, attachmentId: string) => Promise<unknown>;
  /**
   * Query keys to invalidate after successful link.
   * Example: [['complaint', id], ['complaints']]
   */
  invalidateQueryKeys?: (readonly unknown[])[];
  successEntityLabel?: string;
}

export default function ComplaintLinkAttachmentBrowserDialog({
  open,
  onOpenChange,
  entityId,
  linkedAttachmentIds,
  linkAttachment,
  invalidateQueryKeys = [],
  successEntityLabel = 'record',
}: ComplaintLinkAttachmentBrowserDialogProps) {
  const queryClient = useQueryClient();
  const [selectedDirectoryId, setSelectedDirectoryId] = useState<string | null>(null);
  const [selectedMap, setSelectedMap] = useState<Map<string, string>>(new Map());
  const [isLinking, setIsLinking] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const selectedIds = useMemo(() => new Set(selectedMap.keys()), [selectedMap]);

  const { data: tree = [] } = useQuery({
    queryKey: ['attachment-directories-tree', false],
    queryFn: () => getDirectoryTree(false),
    enabled: open,
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 10,
  });
  const { data: attachmentsData, isLoading: isLoadingAttachments } = useQuery({
    queryKey: [
      'attachments',
      0,
      100,
      [],
      searchQuery,
      undefined,
      undefined,
      undefined,
      undefined,
      false,
      undefined,
      selectedDirectoryId === null ? undefined : selectedDirectoryId,
    ],
    queryFn: () =>
      getAttachments({
        pageIndex: 0,
        pageSize: 100,
        sorting: [],
        searchQuery,
        directory_id: selectedDirectoryId === null ? undefined : selectedDirectoryId,
        is_deleted: false,
      }),
    enabled: open,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const attachments = attachmentsData?.data ?? [];

  const allFolderIds = useMemo(() => collectAllFolderIds(tree), [tree]);
  const handleExpandAll = useCallback(() => setExpandedIds(new Set(allFolderIds)), [allFolderIds]);
  const handleCollapseAll = useCallback(() => setExpandedIds(new Set()), []);
  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const availableAttachments = useMemo(
    () => attachments.filter((a) => !linkedAttachmentIds.has(a.id)),
    [attachments, linkedAttachmentIds]
  );

  const toggleSelection = useCallback((att: Attachment) => {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      if (next.has(att.id)) next.delete(att.id);
      else next.set(att.id, att.original_filename || att.id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedIds.size >= availableAttachments.length) {
      setSelectedMap(new Map());
    } else {
      setSelectedMap(
        new Map(availableAttachments.map((a) => [a.id, a.original_filename || a.id]))
      );
    }
  }, [availableAttachments, selectedIds.size]);

  const clearSelection = useCallback(() => setSelectedMap(new Map()), []);

  const resetOnClose = useCallback(() => {
    setSelectedDirectoryId(null);
    setSelectedMap(new Map());
    setSearchQuery('');
    setExpandedIds(new Set());
  }, []);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) resetOnClose();
      onOpenChange(next);
    },
    [onOpenChange, resetOnClose]
  );

  const handleConfirmLink = async () => {
    if (!entityId || selectedIds.size === 0) {
      toast.error('Select at least one attachment to link.');
      return;
    }

    setIsLinking(true);
    const ids = Array.from(selectedIds);

    try {
      for (const attachmentId of ids) {
        await linkAttachment(entityId, attachmentId);
      }
      for (const queryKey of invalidateQueryKeys) {
        queryClient.invalidateQueries({ queryKey: [...queryKey] });
      }
      toast.success(`${ids.length} attachment(s) linked to ${successEntityLabel}.`);
      handleOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to link attachment(s).');
    } finally {
      setIsLinking(false);
    }
  };

  const selectedList = useMemo(
    () => Array.from(selectedMap.entries()).map(([id, name]) => ({ id, name })),
    [selectedMap]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Link Existing Attachment</DialogTitle>
        </DialogHeader>

        <ResizablePanelGroup
          direction="horizontal"
          className="flex-1 min-h-0 rounded-lg border bg-card"
        >
          <ResizablePanel defaultSize={20} minSize={15} maxSize={45} className="min-w-0">
            <div className="h-full flex flex-col overflow-hidden">
              <div className="px-2 py-2 border-b bg-muted/40 flex items-center justify-between gap-1 shrink-0">
                <span className="text-sm font-medium text-muted-foreground">Folders</span>
                <div className="flex items-center gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={handleExpandAll}
                    title="Expand all"
                    aria-label="Expand all"
                  >
                    <ChevronDown className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={handleCollapseAll}
                    title="Collapse all"
                    aria-label="Collapse all"
                  >
                    <ChevronUp className="size-4" />
                  </Button>
                </div>
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-2">
                  <ReadOnlyFolderTree
                    selectedId={selectedDirectoryId}
                    onSelect={setSelectedDirectoryId}
                    tree={tree}
                    expanded={expandedIds}
                    onToggleExpand={handleToggleExpand}
                  />
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle className="bg-border" />
          <ResizablePanel defaultSize={80} minSize={50} className="min-w-0">
            <div className="h-full flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b bg-muted/40 flex items-center justify-between gap-2 flex-wrap shrink-0">
                <span className="text-sm font-medium text-muted-foreground">Files</span>
                {availableAttachments.length > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={toggleSelectAll}>
                    {selectedIds.size >= availableAttachments.length ? 'Deselect all' : 'Select all'}
                  </Button>
                )}
              </div>
              <div className="px-2 py-2 border-b shrink-0">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    placeholder="Search attachments..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8 pr-8 h-9"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground rounded p-0.5"
                      aria-label="Clear search"
                    >
                      <X className="size-4" />
                    </button>
                  )}
                </div>
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-2">
                  {isLoadingAttachments ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                      <LoaderCircleIcon className="size-5 animate-spin mr-2" />
                      Loading…
                    </div>
                  ) : availableAttachments.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      {attachments.length === 0
                        ? 'No files in this folder.'
                        : 'All files here are already linked to this complaint.'}
                    </div>
                  ) : (
                    <ul className="space-y-0.5">
                      {availableAttachments.map((att) => (
                        <li
                          key={att.id}
                          className={cn(
                            'flex items-center gap-2 rounded-md px-2 py-2 cursor-pointer hover:bg-accent/50',
                            selectedIds.has(att.id) && 'bg-accent/70'
                          )}
                          onClick={() => toggleSelection(att)}
                        >
                          <Checkbox
                            checked={selectedIds.has(att.id)}
                            onCheckedChange={() => toggleSelection(att)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <FileText className="size-4 text-muted-foreground shrink-0" />
                          <span className="truncate text-sm flex-1" title={att.original_filename}>
                            {att.original_filename}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>

        {selectedIds.size > 0 && (
          <div className="rounded-md border bg-muted/30 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-sm font-medium">Selected ({selectedIds.size})</Label>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={clearSelection}>
                <X className="size-3.5 mr-1" />
                Clear
              </Button>
            </div>
            <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">
              {selectedList.map(({ id, name }) => (
                <span
                  key={id}
                  className="inline-flex items-center rounded-md bg-background border px-2 py-0.5 text-xs truncate max-w-[180px]"
                  title={name}
                >
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirmLink}
              disabled={selectedIds.size === 0 || isLinking || !entityId}
          >
            {isLinking ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              `Link ${selectedIds.size > 0 ? selectedIds.size : ''} attachment(s)`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
