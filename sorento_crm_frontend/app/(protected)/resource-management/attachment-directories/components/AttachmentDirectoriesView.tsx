'use client';

import { useId, useState, useMemo } from 'react';
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
import { FileText } from 'lucide-react';
import {
  useDirectoryTree,
  useUpdateAttachment,
} from '../../attachments/hooks/useAttachments';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import DirectoryTreeSidebar from './DirectoryTreeSidebar';
import AttachmentsInFolderPanel from './AttachmentsInFolderPanel';

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

function AttachmentDirectoriesContent({
  selectedId,
  setSelectedId,
  selectedFolderName,
}: {
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  selectedFolderName: string | null;
}) {
  const [activeDrag, setActiveDrag] = useState<{ id: string; name: string } | null>(null);

  useDndMonitor({
    onDragStart: ({ active }) => {
      const id = String(active.id);
      if (!id.startsWith(DND_ID_ATTACHMENT_PREFIX)) return;
      const data = active.data?.current as { attachmentName?: string } | undefined;
      setActiveDrag({ id, name: data?.attachmentName ?? 'Attachment' });
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
          <DirectoryTreeSidebar selectedId={selectedId} onSelect={setSelectedId} />
        </ResizablePanel>
        <ResizableHandle withHandle className="bg-border" />
        <ResizablePanel defaultSize={80} minSize={50} className="min-w-0">
          <div className="h-full overflow-auto p-4">
            <AttachmentsInFolderPanel
              directoryId={selectedId}
              directoryName={selectedFolderName}
            />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
      <DragOverlay dropAnimation={null}>
        {activeDrag ? (
          <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-md">
            <FileText className="size-4 text-muted-foreground shrink-0" />
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
  const dndId = useId();
  const [selectedId, setSelectedId] = useState<string | null>(initialDirectoryId);
  const { data: tree = [] } = useDirectoryTree();
  const updateAttachmentMutation = useUpdateAttachment();
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
    if (!activeId.startsWith(DND_ID_ATTACHMENT_PREFIX)) return;

    const isOverFolder =
      overId === DND_ID_FOLDER_ALL || overId.startsWith(DND_ID_FOLDER_PREFIX);
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
      />
    </DndContext>
  );
}
