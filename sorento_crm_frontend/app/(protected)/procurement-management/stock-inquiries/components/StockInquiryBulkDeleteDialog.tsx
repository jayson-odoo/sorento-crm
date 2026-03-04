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
import { useBulkDeleteStockInquiries } from '../hooks/useStockInquiries';

interface StockInquiryBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  inquiryIds: string[];
  onSuccess?: () => void;
}

export default function StockInquiryBulkDeleteDialog({
  open,
  onOpenChange,
  inquiryIds,
  onSuccess,
}: StockInquiryBulkDeleteDialogProps) {
  const bulkDeleteMutation = useBulkDeleteStockInquiries();

  const handleDelete = () => {
    if (inquiryIds.length === 0) return;
    bulkDeleteMutation.mutate(inquiryIds, {
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
          <DialogTitle>Delete stock inquiries</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {inquiryIds.length} stock inquir
          {inquiryIds.length !== 1 ? 'ies' : 'y'}? This action cannot be undone.
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
            Delete {inquiryIds.length} inquir
            {inquiryIds.length !== 1 ? 'ies' : 'y'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
