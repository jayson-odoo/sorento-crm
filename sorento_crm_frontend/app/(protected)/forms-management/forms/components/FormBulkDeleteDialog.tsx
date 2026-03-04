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
import { useBulkDeleteForms } from '../hooks/useForms';

interface FormBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  formIds: string[];
  onSuccess?: () => void;
}

export default function FormBulkDeleteDialog({
  open,
  onOpenChange,
  formIds,
  onSuccess,
}: FormBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteForms();

  const handleDelete = () => {
    if (formIds.length === 0) return;
    bulkDeleteMutation.mutate(formIds, {
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
          <DialogTitle>Delete forms</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {formIds.length} form
          {formIds.length !== 1 ? 's' : ''}? This action cannot be undone.
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
            Delete {formIds.length} form
            {formIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
