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
import { Label } from '@/components/ui/label';
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
          <DialogTitle>Quantity over the quotation</DialogTitle>
        </DialogHeader>
        {products && products.length > 0 ? (
          <table className="w-full table-fixed text-sm">
            <thead>
              <tr className="text-muted-foreground text-left text-xs">
                <th className="py-1 font-medium">Product</th>
                <th className="w-20 py-1 text-end font-medium">All POs</th>
                <th className="w-20 py-1 text-end font-medium">Quoted</th>
              </tr>
            </thead>
            <tbody>
              {products.map((row, index) => {
                const name = row.product_code ?? row.description ?? '-';
                return (
                  <tr key={`${name}-${index}`} className="border-t">
                    <td className="truncate py-1.5" title={row.description ?? name}>
                      {name}
                    </td>
                    <td className="py-1.5 text-end tabular-nums">{qty(row.ordered)}</td>
                    <td className="py-1.5 text-end tabular-nums">{qty(row.quoted)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
        <div className="space-y-1.5">
          <Label htmlFor="qty-over-reason">Reason</Label>
          <Textarea
            id="qty-over-reason"
            value={reason}
            maxLength={2000}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            type="button"
            disabled={!reason.trim() || isSaving}
            onClick={() => void onSubmit(reason.trim())}
          >
            {isSaving ? 'Saving...' : 'Save with reason'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
