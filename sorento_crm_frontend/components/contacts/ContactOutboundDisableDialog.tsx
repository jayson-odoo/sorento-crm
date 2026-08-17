'use client';

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

interface ContactOutboundDisableDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** How many CONTACTS the action silences - never how many rows were selected. */
  contactCount: number;
  busy?: boolean;
  onConfirm: () => void;
}

/**
 * Confirmation for silencing a selection of contacts.
 *
 * Silencing is destructive in the way that matters here: nobody is told, the
 * messages simply never arrive. So the copy names the number of CONTACTS (the
 * grants grid can have several rows per person) and says plainly what stops.
 */
export default function ContactOutboundDisableDialog({
  open,
  onOpenChange,
  contactCount,
  busy,
  onConfirm,
}: ContactOutboundDisableDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Disable outbound messaging</AlertDialogTitle>
          <AlertDialogDescription>
            {contactCount} contact(s) will receive no WhatsApp messages until outbound is
            switched back on for them.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={busy}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Disable
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
