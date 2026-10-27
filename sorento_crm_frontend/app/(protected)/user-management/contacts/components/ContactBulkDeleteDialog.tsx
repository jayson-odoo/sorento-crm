'use client';

import { LoaderCircleIcon } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { toast } from '@/lib/toast';

interface ContactBulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactIds: string[];
  onSuccess?: () => void;
}

interface BulkDeleteResult {
  deleted_count: number;
  blocked?: { id: string; name: string | null; reason: string }[];
  message: string;
}

export default function ContactBulkDeleteDialog({
  open,
  onOpenChange,
  contactIds,
  onSuccess,
}: ContactBulkDeleteDialogProps) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      const response = await apiFetch('/api/user-management/contacts/bulk', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      if (!response.ok) {
        throw new Error(await extractApiError(response, 'Failed to delete contacts'));
      }
      return response.json();
    },
    onSuccess: (result: BulkDeleteResult) => {
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      const blocked = result?.blocked ?? [];
      if (blocked.length > 0) {
        // Contacts with linked history are kept; name each one and why.
        toast.error(result.message, {
          description: blocked
            .map((b) => `${b.name || 'Unnamed contact'}: ${b.reason}`)
            .join('\n'),
          classNames: { description: 'whitespace-pre-line' },
        });
      } else {
        toast.success(result?.message ?? `${contactIds.length} contact(s) deleted`);
      }
      onOpenChange(false);
      onSuccess?.();
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete contacts');
    },
  });

  const handleDelete = () => {
    if (contactIds.length === 0) return;
    deleteMutation.mutate(contactIds);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete contacts</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Permanently delete {contactIds.length} contact{contactIds.length !== 1 ? 's' : ''}? Related
          access agent assignments will be removed. This action cannot be undone.
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
            {deleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin mr-2 size-4" />
            )}
            Delete {contactIds.length} contact{contactIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
