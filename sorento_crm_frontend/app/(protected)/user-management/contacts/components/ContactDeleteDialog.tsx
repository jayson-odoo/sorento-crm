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
import { toast } from 'sonner';
import type { RespondContact } from '../types/contact.types';

interface ContactDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contact: RespondContact | null;
  onSuccess?: () => void;
}

export default function ContactDeleteDialog({
  open,
  onOpenChange,
  contact,
  onSuccess,
}: ContactDeleteDialogProps) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async (contactId: string) => {
      const response = await apiFetch(`/api/user-management/contacts/${contactId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(await extractApiError(response, 'Failed to delete contact'));
      }
    },
    onSuccess: (_, contactId) => {
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      queryClient.invalidateQueries({ queryKey: ['respond-contact', contactId] });
      toast.success('Contact deleted successfully');
      onOpenChange(false);
      onSuccess?.();
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete contact');
    },
  });

  const handleDelete = () => {
    if (!contact) return;
    deleteMutation.mutate(contact.id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Contact</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete the contact{' '}
          <strong>{contact?.phone_number}</strong>
          {contact?.name ? ` (${contact.name})` : ''}? Related access agent assignments will be
          removed. SLA tracking references will be cleared. This action cannot be undone.
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
            Delete Contact
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
