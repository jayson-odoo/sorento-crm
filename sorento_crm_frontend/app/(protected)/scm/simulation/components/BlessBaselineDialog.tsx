'use client';

import { Loader2 } from 'lucide-react';
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

/**
 * Confirm before overwriting the blessed baseline with the last run. Destructive
 * styling (per ADR-PRODUCT-STANDARDS) because it permanently replaces the reference
 * every future run is diffed against - there is no undo short of re-blessing an
 * earlier run by hand.
 */
export function BlessBaselineDialog({
  open,
  onOpenChange,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Bless this run as the baseline?</AlertDialogTitle>
          <AlertDialogDescription>
            This overwrites the blessed baseline with the last run. This action cannot
            be undone - every scenario currently marked CHANGED, NEW or GONE will read as
            SAME the next time anyone compares against it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={pending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {pending ? <Loader2 className="size-4 animate-spin" /> : null}
            Bless baseline
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
