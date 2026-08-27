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
import { useUnplaceAllOrderInquiryRows } from '../hooks/useOrderInquiry';
import type { UnplaceAllRequest } from '../types/orderInquiry.types';

/**
 * "Unlink all" (the captain, 20-21 Aug): operates on the CURRENT worklist scope - one
 * product when the filters happen to narrow to it, every linked row in the company when
 * they name nothing. `filters` and `count`/`productCode` are the SAME numbers the toolbar
 * button already resolved (`useUnplaceAllPreview`), so what a person confirms and what
 * the commit actually touches can never disagree.
 *
 * `scopeLabels` (S2, code review, 20 Aug 2026) is the caller's own account of which
 * filters actually narrowed this run - `filters` itself always drops `state` (the action
 * is about linked rows whatever State says), so a dialog that called its scope "the
 * current view" was lying the moment State was set to anything: a State=raised screen
 * showing zero linked rows still offered to revert hundreds nobody could see. Named
 * plainly instead: every active filter, or "every linked row" when none narrowed it.
 *
 * S3: the standard "cannot be undone" copy was dropped here on the theory that Auto-place
 * makes this fully re-doable - no longer true once auto-place ranks contenders by policy
 * (`_rank_raised_rows`): a re-run re-deals by the current priority, and a placement a
 * person made BY HAND is destroyed outright (`_unlink_row` also deletes the link claim).
 * The copy says that plainly rather than implying nothing is lost.
 */
export function UnlinkAllOrderInquiryDialog({
  open,
  onOpenChange,
  filters,
  count,
  productCode,
  scopeLabels = [],
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: UnplaceAllRequest;
  count: number;
  productCode?: string | null;
  /** The active filters in play, already human-readable (never a raw id) - `[]` when none narrow the scope. */
  scopeLabels?: string[];
}) {
  const unlinkAll = useUnplaceAllOrderInquiryRows();
  const scope = productCode
    ? `for ${productCode}`
    : scopeLabels.length > 0
      ? scopeLabels.join(', ')
      : 'across the whole company';

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Unlink all</AlertDialogTitle>
          <AlertDialogDescription>
            {count} linked row{count === 1 ? '' : 's'} {scope} will lose every link, ready
            for Auto-link to re-deal them.
            Auto-place will re-deal them by the current priority policy. Placements made
            by hand are not restored.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={unlinkAll.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={unlinkAll.isPending || count === 0}
            onClick={(event) => {
              event.preventDefault();
              unlinkAll.mutate(filters, { onSuccess: () => onOpenChange(false) });
            }}
          >
            {unlinkAll.isPending && (
              <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
            )}
            Unlink all
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
