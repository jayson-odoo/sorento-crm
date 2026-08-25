'use client';

import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useBulkUpdateProducts } from '../hooks/useProducts';

interface ProductBulkChatSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productIds: string[];
  onSuccess?: () => void;
}

/**
 * One bulk action for the chat-search flag, both directions. Hiding is not
 * destructive (the products stay active and on their orders), so the dialog is
 * a plain choice with the count, not a delete-style confirmation.
 */
export default function ProductBulkChatSearchDialog({
  open,
  onOpenChange,
  productIds,
  onSuccess,
}: ProductBulkChatSearchDialogProps) {
  const bulkUpdate = useBulkUpdateProducts();
  const count = productIds.length;
  const noun = `${count} product${count === 1 ? '' : 's'}`;

  const apply = (isSearchable: boolean) => {
    if (count === 0) return;
    bulkUpdate.mutate(
      { ids: productIds, updates: { is_searchable: isSearchable } },
      {
        onSuccess: () => {
          onOpenChange(false);
          onSuccess?.();
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Chat search for {noun}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          A hidden product stays active and on its orders; the chatbot just never
          answers with it, even when its exact code is typed.
        </DialogDescription>
        <DialogFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={() => apply(true)}
            disabled={bulkUpdate.isPending}
          >
            Show in chat
          </Button>
          <Button onClick={() => apply(false)} disabled={bulkUpdate.isPending}>
            {bulkUpdate.isPending && (
              <LoaderCircleIcon className="size-4 animate-spin mr-2" />
            )}
            Hide from chat
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
