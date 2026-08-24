'use client';

import { LoaderCircleIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  useBulkDeleteAttachments,
  useBulkArchiveAttachments,
  useDeleteDirectory,
  usePermanentDeleteDirectory,
} from '../hooks/useAttachments';

interface AttachmentBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentIds: string[];
  /** Selected FOLDER ids - deleted via the directory delete (cascades subtree). */
  folderIds?: string[];
  onSuccess?: () => void;
  /** When true, permanently delete. When false, archive (move to trash). */
  permanent?: boolean;
}

function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count !== 1 ? 's' : ''}`;
}

export default function AttachmentBulkDeleteDialog({
  open,
  onOpenChange,
  attachmentIds,
  folderIds = [],
  onSuccess,
  permanent = false,
}: AttachmentBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteAttachments();
  const bulkArchiveMutation = useBulkArchiveAttachments();
  const deleteDirectoryMutation = useDeleteDirectory();
  const permanentDeleteDirectoryMutation = usePermanentDeleteDirectory();
  const fileMutation = permanent ? bulkDeleteMutation : bulkArchiveMutation;
  const folderMutation = permanent
    ? permanentDeleteDirectoryMutation
    : deleteDirectoryMutation;

  const fileCount = attachmentIds.length;
  const folderCount = folderIds.length;
  const totalCount = fileCount + folderCount;
  const isPending = fileMutation.isPending || folderMutation.isPending;

  const handleAction = async () => {
    if (totalCount === 0) return;
    // Folders cascade their subtree; files use the trash-aware bulk path. Run
    // both, then close once everything settles. The hooks invalidate
    // drive-contents / tree / attachments on each success.
    const tasks: Promise<unknown>[] = [];
    if (fileCount > 0) {
      tasks.push(fileMutation.mutateAsync(attachmentIds));
    }
    for (const id of folderIds) {
      tasks.push(folderMutation.mutateAsync(id));
    }
    const results = await Promise.allSettled(tasks);
    const failed = results.some((r) => r.status === 'rejected');
    if (!failed) {
      onOpenChange(false);
      onSuccess?.();
    }
  };

  // Accurate count summary, e.g. "Delete 3 items: 1 folder, 2 files".
  const itemSummary = (() => {
    const parts: string[] = [];
    if (folderCount > 0) parts.push(pluralize(folderCount, 'folder'));
    if (fileCount > 0) parts.push(pluralize(fileCount, 'file'));
    const breakdown = parts.length > 1 ? ` (${parts.join(', ')})` : '';
    return `${pluralize(totalCount, 'item')}${breakdown}`;
  })();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{permanent ? 'Permanently delete' : 'Move to trash'}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {permanent ? (
            <>
              Permanently delete {itemSummary}? This action cannot be undone.
              {folderCount > 0
                ? ' Each selected folder and all of its contents will be deleted.'
                : ''}
            </>
          ) : (
            <>
              Move {itemSummary} to trash? You can restore them later.
              {folderCount > 0
                ? ' Each selected folder and all of its contents will be moved to trash.'
                : ''}
            </>
          )}
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleAction} disabled={isPending || totalCount === 0}>
            {isPending && <LoaderCircleIcon className="animate-spin mr-2" />}
            {permanent ? 'Permanently Delete' : 'Move to Trash'} {itemSummary}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
