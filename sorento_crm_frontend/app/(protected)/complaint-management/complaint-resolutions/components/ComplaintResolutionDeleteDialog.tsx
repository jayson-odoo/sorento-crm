'use client';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { LoaderCircleIcon } from 'lucide-react';
import { useDeleteComplaintResolution } from '../hooks/useComplaintResolutions';
import type { ComplaintResolution } from '../types/complaintResolution.types';

interface Props {
  open: boolean;
  closeDialog: () => void;
  row: ComplaintResolution;
}

export default function ComplaintResolutionDeleteDialog({ open, closeDialog, row }: Props) {
  const deleteMutation = useDeleteComplaintResolution();
  const handleDelete = () => {
    deleteMutation.mutate(row.id, {
      onSuccess: () => closeDialog(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete the resolution{' '}
          <strong className="text-foreground">{row.name}</strong>? This action cannot be undone.
        </DialogDescription>
        {(row.complaint_count ?? 0) > 0 && (
          <p className="text-sm text-amber-600">
            This resolution is referenced by {row.complaint_count} complaint(s); the deletion will be blocked until they are reassigned.
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && <LoaderCircleIcon className="animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
