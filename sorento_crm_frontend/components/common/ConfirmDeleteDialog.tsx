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
      queryKeysToInvalidate.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
      onSuccessProp?.();
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
        <DialogDescription>{description}</DialogDescription>
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
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
