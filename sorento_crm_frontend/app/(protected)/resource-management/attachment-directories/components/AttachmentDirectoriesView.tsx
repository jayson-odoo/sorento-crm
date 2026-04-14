'use client';

import { useId, useState, useMemo } from 'react';
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
import { FileText, Folder } from 'lucide-react';
import {
  useDirectoryTree,
  useUpdateAttachment,
  useUpdateDirectory,
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
      <ResizablePanelGroup
        direction="horizontal"
        className="flex-1 min-h-0 rounded-lg border bg-card"
      >
        <ResizablePanel defaultSize={20} minSize={15} maxSize={45} className="min-w-0">
          <DirectoryTreeSidebar
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAdjustFolderAccessLevels={(id) => onOpenAccessLevels({ directoryId: id })}
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
  const updateDirectoryMutation = useUpdateDirectory();
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

    const isOverFolder =
      overId === DND_ID_FOLDER_ALL || overId.startsWith(DND_ID_FOLDER_PREFIX);

    // Folder drag: move folder to another folder (reparent)
    if (
      activeId.startsWith(DND_ID_FOLDER_PREFIX) &&
      activeId !== DND_ID_FOLDER_ALL &&
      isOverFolder
    ) {
      const folderId = activeId.slice(DND_ID_FOLDER_PREFIX.length);
      const targetParentId: string | null =
        overId === DND_ID_FOLDER_ALL ? null : overId.slice(DND_ID_FOLDER_PREFIX.length);

      if (folderId === targetParentId) return; // can't drop on self
      const descendants = collectDescendantFolderIds(tree, folderId);
      if (targetParentId && descendants.has(targetParentId)) return; // can't drop onto own descendant

      updateDirectoryMutation.mutate(
        { id: folderId, data: { parent_id: targetParentId } },
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
    const currentDirectoryId =
      (active.data?.current as { currentDirectoryId?: string | null } | undefined)
        ?.currentDirectoryId ?? null;
    if (
      currentDirectoryId === targetDirectoryId ||
      (currentDirectoryId == null && targetDirectoryId == null)
    ) {
      return;
    }
    updateAttachmentMutation.mutate(
      { attachmentId, data: { directory_id: targetDirectoryId } },
      {
        onSuccess: () => {
          const folderLabel =
            targetDirectoryId == null
              ? 'All attachments'
              : findFolderNameById(tree, targetDirectoryId) ?? 'folder';
          toast.success(`Moved to ${folderLabel}`);
        },
      }
    );
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
