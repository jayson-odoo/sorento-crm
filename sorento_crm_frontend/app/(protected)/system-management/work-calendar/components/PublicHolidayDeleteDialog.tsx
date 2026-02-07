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
import { useDeletePublicHoliday } from '../hooks/useWorkCalendar';
import type { PublicHoliday } from '../types/workCalendar.types';

interface PublicHolidayDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  holiday: PublicHoliday | null;
}

export default function PublicHolidayDeleteDialog({
  open,
  onOpenChange,
  holiday,
}: PublicHolidayDeleteDialogProps) {
  const deleteMutation = useDeletePublicHoliday();

  const handleDelete = () => {
    if (holiday) {
      deleteMutation.mutate(holiday.id, {
        onSuccess: () => onOpenChange(false),
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
          Are you sure you want to delete <strong>{holiday?.name}</strong> on{' '}
          <strong>{holiday?.date}</strong>? This action cannot be undone.
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
            {deleteMutation.isPending && <LoaderCircleIcon className="animate-spin mr-2" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
