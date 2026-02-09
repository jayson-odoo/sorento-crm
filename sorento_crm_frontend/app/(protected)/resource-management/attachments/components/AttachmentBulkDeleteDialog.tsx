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
import { useBulkDeleteAttachments } from '../hooks/useAttachments';

interface AttachmentBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentIds: string[];
  onSuccess?: () => void;
}

export default function AttachmentBulkDeleteDialog({
  open,
  onOpenChange,
  attachmentIds,
  onSuccess,
}: AttachmentBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteAttachments();

  const handleDelete = () => {
    if (attachmentIds.length === 0) return;
    bulkDeleteMutation.mutate(attachmentIds, {
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
          <DialogTitle>Confirm bulk delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete {attachmentIds.length} attachment
          {attachmentIds.length !== 1 ? 's' : ''}? This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={bulkDeleteMutation.isPending}
          >
            {bulkDeleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2" />
            )}
            Delete {attachmentIds.length} attachment{attachmentIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
