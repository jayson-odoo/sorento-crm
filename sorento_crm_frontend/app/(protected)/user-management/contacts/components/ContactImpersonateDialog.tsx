'use client';

import { useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { toast } from 'sonner';
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
import { startContactImpersonation } from '@/services/contactImpersonationService';
import type { RespondContact } from '../types/contact.types';

/**
 * "Browse the portal as this contact", confirmed first.
 *
 * One component because the action is offered in two places now (D15): the list
 * row's "..." and the record's gear. Two copies of a confirmation are two chances
 * to word the same consequence differently.
 */
export function ContactImpersonateDialog({
  contact,
  onClose,
}: {
  contact: RespondContact | null;
  onClose: () => void;
}) {
  const [starting, setStarting] = useState(false);
  const label = contact?.name || contact?.phone_number || contact?.id || '';

  return (
    <AlertDialog
      open={!!contact}
      onOpenChange={(open) => {
        if (!open && !starting) onClose();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirm Impersonation</AlertDialogTitle>
          <AlertDialogDescription>
            You will browse the portal as <strong>{label}</strong> with their access
            rights. All records you create or modify will still be attributed to you.
            Continue?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={starting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={starting}
            onClick={async (event) => {
              event.preventDefault();
              if (!contact) return;
              setStarting(true);
              try {
                const session = await startContactImpersonation(contact.id);
                toast.success(`Now impersonating ${label}`);
                onClose();
                if (typeof window !== 'undefined') {
                  window.open(session.portalUrl, '_blank', 'noopener,noreferrer');
                }
              } catch (err) {
                toast.error(
                  err instanceof Error ? err.message : 'Failed to start impersonation',
                );
              } finally {
                setStarting(false);
              }
            }}
          >
            {starting ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Starting...
              </>
            ) : (
              'Impersonate'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
