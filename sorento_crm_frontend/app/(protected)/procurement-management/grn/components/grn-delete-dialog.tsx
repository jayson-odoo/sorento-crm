'use client';

import { useState } from 'react';
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
import { useDeleteGRN } from '../hooks/useGRN';
import type { GRN } from '../types/grn.types';

interface GRNDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  grn: GRN;
  onSuccess?: () => void;
}

export default function GRNDeleteDialog({
  open,
  closeDialog,
  grn,
  onSuccess,
}: GRNDeleteDialogProps) {
  const deleteMutation = useDeleteGRN();

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(grn.id);
      closeDialog();
      if (onSuccess) {
        onSuccess();
      }
    } catch (error) {
      // Error is handled by the mutation (toast notification)
    }
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete GRN?</DialogTitle>
          <DialogDescription>
            GRN <strong>{grn.picking_number}</strong> is deleted for good. This
            cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
            Keep GRN
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2" />
            )}
            Delete GRN
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
