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
import { useBulkDeleteAttachments, useBulkArchiveAttachments } from '../hooks/useAttachments';

interface AttachmentBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentIds: string[];
  onSuccess?: () => void;
  /** When true, permanently delete. When false, archive (move to trash). */
  permanent?: boolean;
}

export default function AttachmentBulkDeleteDialog({
  open,
  onOpenChange,
  attachmentIds,
  onSuccess,
  permanent = false,
}: AttachmentBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteAttachments();
  const bulkArchiveMutation = useBulkArchiveAttachments();
  const mutation = permanent ? bulkDeleteMutation : bulkArchiveMutation;

  const handleAction = () => {
    if (attachmentIds.length === 0) return;
    mutation.mutate(attachmentIds, {
      onSuccess: () => {
        onOpenChange(false);
        onSuccess?.();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {permanent ? 'Permanently delete' : 'Move to trash'}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {permanent ? (
            <>
              Permanently delete {attachmentIds.length} attachment
              {attachmentIds.length !== 1 ? 's' : ''}? This action cannot be undone.
            </>
          ) : (
            <>
              Move {attachmentIds.length} attachment{attachmentIds.length !== 1 ? 's' : ''} to trash?
              You can restore them later.
            </>
          )}
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleAction}
            disabled={mutation.isPending}
          >
            {mutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2" />
            )}
            {permanent ? 'Permanently Delete' : 'Move to Trash'} {attachmentIds.length} attachment
            {attachmentIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
