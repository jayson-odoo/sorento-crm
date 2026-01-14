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
import { useDeletePackingList } from '../hooks/usePackingLists';
import type { PackingList } from '../types/packingList.types';

interface PackingListDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  packingList: PackingList;
  onSuccess?: () => void;
}

export default function PackingListDeleteDialog({
  open,
  closeDialog,
  packingList,
  onSuccess,
}: PackingListDeleteDialogProps) {
  const deleteMutation = useDeletePackingList();

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(packingList.id);
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
          <DialogTitle>Confirm Delete</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete the packing list{' '}
            <strong>{packingList.shipment_number}</strong>? This action cannot be
            undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
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
