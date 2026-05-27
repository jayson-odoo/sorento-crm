'use client';

import { useId, useState, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  useDndMonitor,
  type DragEndEvent,
} from '@dnd-kit/core';
import { toast } from 'sonner';
import { FileText, Folder, PanelLeftOpen } from 'lucide-react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { Button } from '@/components/ui/button';
import {
  useBulkMoveAttachments,
  useDirectoryTree,
  useMoveDirectory,
  useUpdateAttachment,
} from '../../attachments/hooks/useAttachments';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import DirectoryTreeSidebar from './DirectoryTreeSidebar';
import AttachmentsInFolderPanel from './AttachmentsInFolderPanel';
import BulkAttachmentAccessLevelsDialog, {
  type BulkAccessLevelsScope,
} from './BulkAttachmentAccessLevelsDialog';

export const DND_ID_ATTACHMENT_PREFIX = 'attachment-';
export const DND_ID_FOLDER_PREFIX = 'folder-';
export const DND_ID_FOLDER_ALL = 'folder-all';
export const DND_ID_FOLDER_BETWEEN_PREFIX = 'folder-between::';

function parseBetweenId(id: string): { parentId: string | null; index: number } | null {
  if (!id.startsWith(DND_ID_FOLDER_BETWEEN_PREFIX)) return null;
  const rest = id.slice(DND_ID_FOLDER_BETWEEN_PREFIX.length);
  const sep = rest.lastIndexOf('::');
  if (sep === -1) return null;
  const parent = rest.slice(0, sep);
  const idx = Number(rest.slice(sep + 2));
  if (!Number.isFinite(idx)) return null;
  return { parentId: parent === 'root' ? null : parent, index: idx };
}

function findFolderNameById(nodes: AttachmentDirectoryTreeNode[], id: string): string | null {
  for (const node of nodes) {
    if (node.id === id) return node.name;
    const found = findFolderNameById(node.children || [], id);
    if (found != null) return found;
  }
  return null;
}

function collectDescendantFolderIds(
  nodes: AttachmentDirectoryTreeNode[],
  folderId: string
): Set<string> {
  const ids = new Set<string>();
  function addSubtree(node: AttachmentDirectoryTreeNode) {
    if (node.children?.length) {
      node.children.forEach((c) => {
        ids.add(c.id);
        addSubtree(c);
      });
    }
  }
  function findAndCollect(nodes: AttachmentDirectoryTreeNode[]): boolean {
    for (const node of nodes) {
      if (node.id === folderId) {
        addSubtree(node);
        return true;
      }
      if (node.children?.length && findAndCollect(node.children)) return true;
    }
    return false;
  }
  findAndCollect(nodes);
  return ids;
}

function AttachmentDirectoriesContent({
  selectedId,
  setSelectedId,
  selectedFolderName,
  onOpenAccessLevels,
}: {
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  selectedFolderName: string | null;
  onOpenAccessLevels: (scope: BulkAccessLevelsScope) => void;
}) {
  const [activeDrag, setActiveDrag] = useState<{
    id: string;
    name: string;
    type: 'attachment' | 'folder';
  } | null>(null);
  const sidebarPanelRef = useRef<ImperativePanelHandle>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useDndMonitor({
    onDragStart: ({ active }) => {
      const id = String(active.id);
      const data = active.data?.current as { attachmentName?: string; folderName?: string } | undefined;
      if (id.startsWith(DND_ID_ATTACHMENT_PREFIX)) {
        setActiveDrag({ id, name: data?.attachmentName ?? 'Attachment', type: 'attachment' });
      } else if (id.startsWith(DND_ID_FOLDER_PREFIX) && id !== DND_ID_FOLDER_ALL) {
        setActiveDrag({ id, name: data?.folderName ?? 'Folder', type: 'folder' });
      }
    },
    onDragEnd: () => setActiveDrag(null),
    onDragCancel: () => setActiveDrag(null),
  });

  return (
    <>
      <div className="relative flex-1 min-h-0">
        {sidebarCollapsed && (
          <Button
            variant="outline"
            size="sm"
            className="absolute left-2 top-2 z-20 gap-1 shadow-sm"
            onClick={() => sidebarPanelRef.current?.expand()}
            title="Show folders panel"
          >
            <PanelLeftOpen className="size-4" />
            Folders
          </Button>
        )}
        <ResizablePanelGroup
        direction="horizontal"
        className="h-full rounded-lg border bg-card"
      >
        <ResizablePanel
          ref={sidebarPanelRef}
          collapsible
          collapsedSize={0}
          defaultSize={20}
          minSize={15}
          maxSize={45}
          className="min-w-0"
          onCollapse={() => setSidebarCollapsed(true)}
          onExpand={() => setSidebarCollapsed(false)}
        >
          <DirectoryTreeSidebar
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAdjustFolderAccessLevels={(id) => onOpenAccessLevels({ directoryId: id })}
            onCollapsePanel={() => sidebarPanelRef.current?.collapse()}
          />
        </ResizablePanel>
        <ResizableHandle withHandle className="bg-border" />
        <ResizablePanel defaultSize={80} minSize={50} className="min-w-0">
          <div className="h-full overflow-auto p-4">
            <AttachmentsInFolderPanel
              directoryId={selectedId}
              directoryName={selectedFolderName}
              onSelectFolder={setSelectedId}
              onBulkAdjustAccessLevels={(ids) => onOpenAccessLevels({ attachmentIds: ids })}
            />
          </div>
        </ResizablePanel>
        </ResizablePanelGroup>
      </div>
      <DragOverlay dropAnimation={null}>
        {activeDrag ? (
          <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-md">
            {activeDrag.type === 'folder' ? (
              <Folder className="size-4 text-muted-foreground shrink-0" />
            ) : (
              <FileText className="size-4 text-muted-foreground shrink-0" />
            )}
            <span className="text-sm truncate max-w-[200px]">{activeDrag.name}</span>
          </div>
        ) : null}
      </DragOverlay>
    </>
  );
}

export default function AttachmentDirectoriesView({
  initialDirectoryId = null,
}: {
  initialDirectoryId?: string | null;
}) {
  const queryClient = useQueryClient();
  const dndId = useId();
  const [selectedId, setSelectedId] = useState<string | null>(initialDirectoryId);
  const [accessLevelsScope, setAccessLevelsScope] = useState<BulkAccessLevelsScope>(null);
  const { data: tree = [] } = useDirectoryTree();
  const updateAttachmentMutation = useUpdateAttachment();
  const bulkMoveMutation = useBulkMoveAttachments();
  const moveDirectoryMutation = useMoveDirectory();
  const selectedFolderName = useMemo(
    () => (selectedId ? findFolderNameById(tree, selectedId) : null),
    [selectedId, tree]
  );

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const activeId = String(active.id);
    const overId = String(over.id);

    const isBetween = overId.startsWith(DND_ID_FOLDER_BETWEEN_PREFIX);
    const isOverFolder =
      overId === DND_ID_FOLDER_ALL || (overId.startsWith(DND_ID_FOLDER_PREFIX) && !isBetween);

    const isFolderDrag =
      activeId.startsWith(DND_ID_FOLDER_PREFIX) &&
      !activeId.startsWith(DND_ID_FOLDER_BETWEEN_PREFIX) &&
      activeId !== DND_ID_FOLDER_ALL;

    // Folder drag: reorder between siblings
    if (isFolderDrag && isBetween) {
      const parsed = parseBetweenId(overId);
      if (!parsed) return;
      const folderId = activeId.slice(DND_ID_FOLDER_PREFIX.length);
      if (folderId === parsed.parentId) return;
      const descendants = collectDescendantFolderIds(tree, folderId);
      if (parsed.parentId && descendants.has(parsed.parentId)) return;

      moveDirectoryMutation.mutate(
        { id: folderId, parent_id: parsed.parentId, position: parsed.index },
        {
          onSuccess: () => {
            const targetLabel =
              parsed.parentId == null
                ? 'top level'
                : findFolderNameById(tree, parsed.parentId) ?? 'folder';
            toast.success(`Folder reordered under ${targetLabel}`);
          },
        }
      );
      return;
    }

    // Folder drag: nest into another folder (reparent, append at end)
    if (isFolderDrag && isOverFolder) {
      const folderId = activeId.slice(DND_ID_FOLDER_PREFIX.length);
      const targetParentId: string | null =
        overId === DND_ID_FOLDER_ALL ? null : overId.slice(DND_ID_FOLDER_PREFIX.length);

      if (folderId === targetParentId) return; // can't drop on self
      const descendants = collectDescendantFolderIds(tree, folderId);
      if (targetParentId && descendants.has(targetParentId)) return; // can't drop onto own descendant

      moveDirectoryMutation.mutate(
        { id: folderId, parent_id: targetParentId, position: null },
        {
          onSuccess: () => {
            const targetLabel =
              targetParentId == null
                ? 'All attachments'
                : findFolderNameById(tree, targetParentId) ?? 'folder';
            toast.success(`Folder moved to ${targetLabel}`);
          },
        }
      );
      return;
    }

    // Attachment drag: move file to folder
    if (!activeId.startsWith(DND_ID_ATTACHMENT_PREFIX)) return;
    if (!isOverFolder) return;

    const targetDirectoryId: string | null =
      overId === DND_ID_FOLDER_ALL ? null : overId.slice(DND_ID_FOLDER_PREFIX.length);
    const attachmentId = activeId.slice(DND_ID_ATTACHMENT_PREFIX.length);
    const dragData = active.data?.current as
      | { currentDirectoryId?: string | null; attachmentIds?: string[] }
      | undefined;
    const currentDirectoryId = dragData?.currentDirectoryId ?? null;
    if (
      currentDirectoryId === targetDirectoryId ||
      (currentDirectoryId == null && targetDirectoryId == null)
    ) {
      return;
    }
    const batchIds = dragData?.attachmentIds && dragData.attachmentIds.length > 1
      ? dragData.attachmentIds
      : [attachmentId];
    const folderLabel =
      targetDirectoryId == null
        ? 'All attachments'
        : findFolderNameById(tree, targetDirectoryId) ?? 'folder';
    if (batchIds.length > 1) {
      bulkMoveMutation.mutate(
        { attachmentIds: batchIds, directoryId: targetDirectoryId },
        {
          onSuccess: ({ updated }) => {
            toast.success(`Moved ${updated} file(s) to ${folderLabel}`);
          },
        }
      );
    } else {
      updateAttachmentMutation.mutate(
        { attachmentId, data: { directory_id: targetDirectoryId } },
        {
          onSuccess: () => {
            toast.success(`Moved to ${folderLabel}`);
          },
        }
      );
    }
  };

  return (
    <DndContext id={dndId} sensors={sensors} onDragEnd={handleDragEnd}>
      <AttachmentDirectoriesContent
        selectedId={selectedId}
        setSelectedId={setSelectedId}
        selectedFolderName={selectedFolderName}
        onOpenAccessLevels={setAccessLevelsScope}
      />
      <BulkAttachmentAccessLevelsDialog
        open={accessLevelsScope !== null}
        onOpenChange={(open) => {
          if (!open) setAccessLevelsScope(null);
        }}
        scope={accessLevelsScope}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['attachments'] })}
      />
    </DndContext>
  );
}
