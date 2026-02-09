'use client';

import { useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useDeleteContactAgentAccess } from '../hooks/useAccessAgents';
import type { ContactAgentAccess } from '../types/accessAgent.types';

export interface ContactAgentAccessDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  accessAgentId: string;
  contactAccess: ContactAgentAccess;
}

const ContactAgentAccessDeleteDialog = ({
  open,
  closeDialog,
  accessAgentId,
  contactAccess,
}: ContactAgentAccessDeleteDialogProps) => {
  const deleteMutation = useDeleteContactAgentAccess();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMutation.mutateAsync({ agentId: accessAgentId, contactId: contactAccess.id });
      closeDialog();
    } catch (error) {
      // Error is handled by the mutation hook
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={closeDialog}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirm Delete</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete the contact access agent for{' '}
            <strong className="text-foreground">{contactAccess.respond_contact_phone}</strong>? This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default ContactAgentAccessDeleteDialog;
