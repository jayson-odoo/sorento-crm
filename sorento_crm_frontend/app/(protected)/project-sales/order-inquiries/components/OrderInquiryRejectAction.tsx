'use client';

import * as React from 'react';
import { Ban } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RejectOrderInquiryDialog } from '../../_shared/components/RejectOrderInquiryDialog';
import { isRejectable } from '../../_shared/lib/orderInquiryAck';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

/**
 * The per-row Reject (AC-H5): a button that opens the reason dialog, never a one-click
 * refusal. Absent on a row already rejected - there is nothing left to refuse.
 */
export function OrderInquiryRejectAction({ row }: { row: OrderInquiryWorklistRow }) {
  const [open, setOpen] = React.useState(false);
  if (!isRejectable(row)) return null;
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-destructive"
        onClick={() => setOpen(true)}
      >
        <Ban className="size-3.5" aria-hidden />
        Reject
      </Button>
      {open ? (
        <RejectOrderInquiryDialog
          rowId={row.id}
          itemCode={row.item_code}
          open
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}

export default OrderInquiryRejectAction;
