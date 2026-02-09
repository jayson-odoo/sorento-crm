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
import { useDeleteAttachment } from '../hooks/useAttachments';
import type { Attachment } from '../types/attachment.types';

interface AttachmentDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachment: Attachment | null;
}

export default function AttachmentDeleteDialog({
  open,
  onOpenChange,
  attachment,
}: AttachmentDeleteDialogProps) {
  const deleteMutation = useDeleteAttachment();

  const handleDelete = () => {
    if (attachment) {
      deleteMutation.mutate(attachment.id, {
        onSuccess: () => {
          onOpenChange(false);
        },
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete the attachment{' '}
          <strong>{attachment?.original_filename}</strong>? This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2" />
            )}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
