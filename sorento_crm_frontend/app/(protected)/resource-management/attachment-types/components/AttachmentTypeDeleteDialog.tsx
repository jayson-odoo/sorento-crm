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
import { useDeleteAttachmentType } from '../hooks/useAttachmentTypes';
import type { AttachmentType } from '../types/attachmentType.types';

interface AttachmentTypeDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentType: AttachmentType | null;
}

export default function AttachmentTypeDeleteDialog({
  open,
  onOpenChange,
  attachmentType,
}: AttachmentTypeDeleteDialogProps) {
  const deleteMutation = useDeleteAttachmentType();

  const handleDelete = () => {
    if (attachmentType) {
      deleteMutation.mutate(attachmentType.id, {
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
          Are you sure you want to delete the attachment type{' '}
          <strong>{attachmentType?.type_name}</strong>? This action cannot be undone.
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
