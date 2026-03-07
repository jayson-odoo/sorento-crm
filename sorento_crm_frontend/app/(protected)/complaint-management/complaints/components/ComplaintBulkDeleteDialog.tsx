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
import { useBulkDeleteComplaints } from '../hooks/useComplaints';

interface ComplaintBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  complaintIds: string[];
  onSuccess?: () => void;
}

export default function ComplaintBulkDeleteDialog({
  open,
  onOpenChange,
  complaintIds,
  onSuccess,
}: ComplaintBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteComplaints();

  const handleDelete = () => {
    if (complaintIds.length === 0) return;
    bulkDeleteMutation.mutate(complaintIds, {
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
          <DialogTitle>Delete complaints</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {complaintIds.length} complaint
          {complaintIds.length !== 1 ? 's' : ''}? This action cannot be undone.
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
            Delete {complaintIds.length} complaint
            {complaintIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
