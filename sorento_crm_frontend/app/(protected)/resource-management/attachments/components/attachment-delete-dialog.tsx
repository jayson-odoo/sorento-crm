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
import { useDeleteAttachment, useArchiveAttachment } from '../hooks/useAttachments';
import type { Attachment } from '../types/attachment.types';

interface AttachmentDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachment: Attachment | null;
  /** When true, permanently delete. When false, archive (move to trash). */
  permanent?: boolean;
  /** Called after successful delete/archive (e.g. to close parent modal) */
  onSuccess?: () => void;
}

export default function AttachmentDeleteDialog({
  open,
  onOpenChange,
  attachment,
  permanent = false,
  onSuccess,
}: AttachmentDeleteDialogProps) {
  const deleteMutation = useDeleteAttachment();
  const archiveMutation = useArchiveAttachment();
  const mutation = permanent ? deleteMutation : archiveMutation;

  const handleAction = () => {
    if (attachment) {
      mutation.mutate(attachment.id, {
        onSuccess: () => {
          onOpenChange(false);
          onSuccess?.();
        },
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{permanent ? 'Permanently Delete' : 'Move to Trash'}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {permanent ? (
            <>
              Are you sure you want to permanently delete <strong>{attachment?.original_filename}</strong>? This
              action cannot be undone.
            </>
          ) : (
            <>
              Move <strong>{attachment?.original_filename}</strong> to trash? You can restore it later.
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
            {permanent ? 'Permanently Delete' : 'Move to Trash'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
