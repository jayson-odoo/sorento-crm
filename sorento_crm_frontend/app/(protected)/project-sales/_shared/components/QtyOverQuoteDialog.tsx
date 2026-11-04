'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import type { QtyOverProduct } from '../lib/qtyOverQuote';

function qty(value: string): string {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : value;
}

/**
 * PS-PROPOSAL-QUOTATION soft stop: the project's POs order more of a product than the quotation
 * quotes. One reason per PO, and with it the save goes through. Never a block.
 */
export function QtyOverQuoteDialog({
  products,
  isSaving,
  onCancel,
  onSubmit,
}: {
  /** Null keeps the dialog closed. */
  products: QtyOverProduct[] | null;
  isSaving: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = React.useState('');
  const open = products !== null;
  React.useEffect(() => {
    if (open) setReason('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>More than quoted</DialogTitle>
        </DialogHeader>
        {/* Owner 23:15: one line per product and one reason box, nothing else. */}
        {products && products.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {products.map((row, index) => {
              const name = row.product_code ?? row.description ?? '-';
              return (
                <li key={`${name}-${index}`} className="break-words">
                  {`${name}: ${qty(row.ordered)} ordered, ${qty(row.quoted)} quoted.`}
                </li>
              );
            })}
          </ul>
        ) : null}
        <Textarea
          id="qty-over-reason"
          aria-label="Reason"
          placeholder="Reason"
          value={reason}
          maxLength={2000}
          rows={2}
          onChange={(event) => setReason(event.target.value)}
        />
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!reason.trim() || isSaving}
            onClick={() => void onSubmit(reason.trim())}
          >
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
