'use client';

import * as React from 'react';
import { ChevronDown, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { HistoryUploadDialog } from '../../../scm/reorder/components/HistoryUploadDialog';
import { OutstandingUploadDialog } from '../../../scm/reorder/components/OutstandingUploadDialog';

/**
 * The two books purchasing feeds, on purchasing's own page (AC-H12).
 *
 * The captain, 27 August 2026: Joey uploads the PO and SPO books from Order Inquiries,
 * stays there, and links from there. So these are the SAME two dialogs their home pages
 * mount - `OutstandingUploadDialog` for the outstanding purchase-order book (the purchase
 * orders list' own action) and `HistoryUploadDialog` for the PO & SPO book (the reorder
 * page's), which is where an `SPO-` document becomes an `spo_allocations` row. Same
 * components, same worker jobs, same upload activity drawer: a second uploader here would
 * be a second idea of what a book is.
 *
 * The sales-order book is deliberately NOT offered. It is CS's document, and the plan's
 * whole point is that the two desks own different halves.
 */
export function OrderInquiryUploadMenu({ onQueued }: { onQueued?: () => void }) {
  const [channel, setChannel] = React.useState<'purchase-orders' | 'purchase-history' | null>(
    null,
  );

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">
            <Upload className="size-4" aria-hidden />
            Upload
            <ChevronDown className="size-3.5 opacity-60" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel>Books</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => setChannel('purchase-orders')}>
            <div className="flex flex-col gap-0.5">
              <span>Upload purchase orders</span>
              <span className="text-2xs text-muted-foreground">
                What suppliers still owe us
              </span>
            </div>
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setChannel('purchase-history')}>
            <div className="flex flex-col gap-0.5">
              <span>Upload the PO and SPO book</span>
              <span className="text-2xs text-muted-foreground">
                Shipping orders and past purchases
              </span>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {channel === 'purchase-orders' ? (
        <OutstandingUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          kind="purchase-orders"
          onQueued={onQueued}
        />
      ) : null}
      {channel === 'purchase-history' ? (
        <HistoryUploadDialog
          open
          onOpenChange={(next) => !next && setChannel(null)}
          kind="purchase-history"
          onQueued={onQueued}
        />
      ) : null}
    </>
  );
}

export default OrderInquiryUploadMenu;
