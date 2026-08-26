'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { LoaderCircleIcon } from 'lucide-react';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

/**
 * Reusable delete confirmation dialog per ADR-PRODUCT-STANDARDS.
 * Cancel (outline) left, Delete (destructive) right.
 */
export interface ConfirmDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description: React.ReactNode;
  onDelete: () => Promise<void>;
  queryKeysToInvalidate?: unknown[][];
  successMessage?: string;
  /** The confirm button's own word. Defaults to Delete; a detach or a forget says what it
   *  actually does, so the button and the question in the description agree. */
  confirmLabel?: string;
  /** Called after successful delete (before closing) */
  onSuccess?: () => void;
}

export function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title = 'Confirm delete',
  description,
  onDelete,
  queryKeysToInvalidate = [],
  successMessage = 'Deleted successfully',
  confirmLabel = 'Delete',
  onSuccess,
}: ConfirmDeleteDialogProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: onDelete,
    onSuccess: () => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>{successMessage}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center', duration: 5000 },
      );
      // Let callers navigate/unmount before invalidating (avoids refetching deleted entity detail).
      onSuccess?.();
      queryKeysToInvalidate.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center' },
      );
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {/* `break-words` is load-bearing: descriptions quote the record's own name, and a
            long unbroken filename (an exported CSV, say) has no spaces to wrap at, so it
            ran past the dialog and pushed a horizontal scrollbar under the buttons. */}
        <DialogDescription className="break-words">{description}</DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && <LoaderCircleIcon className="animate-spin me-2 size-4" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
