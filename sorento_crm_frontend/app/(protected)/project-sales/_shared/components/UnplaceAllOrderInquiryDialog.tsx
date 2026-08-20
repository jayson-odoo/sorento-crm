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
 * "Unplace all" (the captain, 20-21 Aug): operates on the CURRENT worklist scope - one
 * product when the filters happen to narrow to it, every placed row in the company when
 * they name nothing. `filters` and `count`/`productCode` are the SAME numbers the toolbar
 * button already resolved (`useUnplaceAllPreview`), so what a person confirms and what
 * the commit actually touches can never disagree. Confirmed like any bulk write - it
 * releases real PO-line claims - but the standard "This action cannot be undone" copy is
 * wrong here: it IS re-doable, through the very Auto-place button beside it.
 */
export function UnplaceAllOrderInquiryDialog({
  open,
  onOpenChange,
  filters,
  count,
  productCode,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: UnplaceAllRequest;
  count: number;
  productCode?: string | null;
}) {
  const unplaceAll = useUnplaceAllOrderInquiryRows();
  const scope = productCode ? `for ${productCode}` : 'in the current view';

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Unplace all</AlertDialogTitle>
          <AlertDialogDescription>
            {count} placed row{count === 1 ? '' : 's'} {scope} will return to raised.
            Auto-place can re-place them.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={unplaceAll.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={unplaceAll.isPending || count === 0}
            onClick={(event) => {
              event.preventDefault();
              unplaceAll.mutate(filters, { onSuccess: () => onOpenChange(false) });
            }}
          >
            {unplaceAll.isPending && (
              <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
            )}
            Unplace all
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
