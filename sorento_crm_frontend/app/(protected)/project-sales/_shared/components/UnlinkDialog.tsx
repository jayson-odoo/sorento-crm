'use client';

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
import { useOrderInquiryPlacementMutations } from '../hooks/useOrderInquiry';

/**
 * Unlink (AC-I1, PLAN-scm-cs-planning-uat.md section 3.I). Confirmed, per the design
 * mandate that every detach is confirmed: it removes a deliberate, evidence-carrying
 * link, the audit claim behind it goes with it, and the quantity returns to demand.
 *
 * With a `linkId` it removes THAT link and leaves the row's others - a row linked across
 * two purchase orders can give one of them back. Without one it removes every link the
 * row holds, which is what the whole-row action means.
 */
export function UnlinkDialog({
  open,
  onOpenChange,
  rowId,
  linkId,
  documentNumber,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rowId: string;
  /** One link, or every link the row holds when omitted. */
  linkId?: string | null;
  /** What to name in the confirm - the document this link sits on. */
  documentNumber?: string | null;
}) {
  const { unplace } = useOrderInquiryPlacementMutations();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Unlink</AlertDialogTitle>
          <AlertDialogDescription>
            {documentNumber
              ? `Remove the link to ${documentNumber}? That quantity goes back to demand, and the next reorder suggestion counts it again.`
              : 'Remove this row’s links? The quantity goes back to demand, and the next reorder suggestion counts it again.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={unplace.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              unplace.mutate(
                { rowId, linkId: linkId ?? undefined },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={unplace.isPending}
          >
            {unplace.isPending && <LoaderCircleIcon className="mr-2 size-4 animate-spin" />}
            Unlink
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
