'use client';

import { useState, useMemo } from 'react';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import TrashTreeSidebar, { TRASH_VIEW_ID, TRASH_FOLDER_PREFIX } from './TrashTreeSidebar';
import AttachmentsInFolderPanel from '../../attachment-directories/components/AttachmentsInFolderPanel';
import { useDirectoryTree } from '../../attachments/hooks/useAttachments';

function findFolderNameById(nodes: AttachmentDirectoryTreeNode[], id: string): string | null {
  for (const node of nodes) {
    if (node.id === id) return node.name;
    const found = findFolderNameById(node.children || [], id);
    if (found != null) return found;
  }
  return null;
}

export default function TrashView() {
  const [selectedId, setSelectedId] = useState<string | null>(TRASH_VIEW_ID);
  const { data: deletedTree = [] } = useDirectoryTree(true);

  const selectedFolderName = useMemo(() => {
    if (!selectedId || selectedId === TRASH_VIEW_ID) return 'Trash';
    if (selectedId.startsWith(TRASH_FOLDER_PREFIX)) {
      const folderId = selectedId.slice(TRASH_FOLDER_PREFIX.length);
      return findFolderNameById(deletedTree, folderId) ?? 'Trash folder';
    }
    return null;
  }, [selectedId, deletedTree]);

  return (
    <ResizablePanelGroup
      direction="horizontal"
      className="flex-1 min-h-0 rounded-lg border bg-card"
    >
      <ResizablePanel defaultSize={20} minSize={15} maxSize={45} className="min-w-0">
        <TrashTreeSidebar selectedId={selectedId} onSelect={setSelectedId} />
      </ResizablePanel>
      <ResizableHandle withHandle className="bg-border" />
      <ResizablePanel defaultSize={80} minSize={50} className="min-w-0">
        <div className="h-full overflow-auto p-4">
          <AttachmentsInFolderPanel
            directoryId={selectedId}
            directoryName={selectedFolderName}
            onRestoreFolder={() => setSelectedId(TRASH_VIEW_ID)}
          />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
