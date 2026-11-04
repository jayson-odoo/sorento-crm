'use client';

import { useState } from 'react';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SoCustomerProject } from '@/components/common/SoCustomerProject';
import { useResetSalesOrderPlanning } from '../../hooks/useSalesOrders';

/**
 * Reset planning (the captain, 27 Aug): a UAT walk has to be repeatable from the screen.
 * Shared by the Sales Orders and Consignments lists (CONSIGN-PLAN), so there is one dialog
 * and one importer of the retired confirm dialog.
 *
 * KEPT as a dialog where S6b turned single-record deletes into grace windows (D7). Two
 * reasons, either of them enough: it acts on a SELECTION of orders, and one countdown cannot
 * speak for a set; and it collects an answer ("also rewind the book"), which a countdown has
 * nowhere to put.
 */
export function ResetPlanningDialog({
  open,
  onOpenChange,
  orders,
  onDone,
  docLabel = 'sales order',
  offerRewind = true,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orders: Array<{
    id: string;
    so_number: string;
    customer_name?: string | null;
    project_label?: string | null;
  }>;
  onDone: () => void;
  /** What one order is called on the calling list ("consignment"). */
  docLabel?: string;
  /** The upload rewind only exists for the sales-order book; a consignment is never uploaded. */
  offerRewind?: boolean;
}) {
  const [rewindBook, setRewindBook] = useState(false);
  const resetMut = useResetSalesOrderPlanning();

  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setRewindBook(false);
      }}
      title="Reset planning"
      confirmLabel="Reset planning"
      description={
        <span className="flex flex-col gap-3">
          <span>
            Put {orders.length === 1 ? 'this' : `these ${orders.length}`} back to never
            planned? Every order inquiry, link, allocation, stock transfer and confirmed
            revision on {orders.length === 1 ? 'it' : 'them'} is removed. The {docLabel} and
            its lines stay. This cannot be undone.
          </span>
          {/* OI-UX-FILTER-SNAPSHOT: each order with its customer / project. */}
          <span className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
            {orders.map((o) => (
              <span key={o.id} className="min-w-0">
                <span className="block truncate font-medium tabular-nums">{o.so_number}</span>
                <SoCustomerProject customer={o.customer_name} project={o.project_label} />
              </span>
            ))}
          </span>
          {offerRewind ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={rewindBook}
                onChange={(e) => setRewindBook(e.target.checked)}
              />
              <span>
                Also put the lines a sales-order upload changed back to before
                the first upload
              </span>
            </label>
          ) : null}
        </span>
      }
      onDelete={async () => {
        for (const o of orders) {
          await resetMut.mutateAsync({
            id: o.id,
            rewindBook: offerRewind && rewindBook,
          });
        }
      }}
      successMessage="Planning reset"
      onSuccess={onDone}
    />
  );
}
