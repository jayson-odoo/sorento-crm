'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { createOrderInquiryReserveRequest } from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` 3.7 (AC-RS-22/AC-RS-23): one line per selected row,
 * Requested defaulted to remaining (never above it), Location defaulted to the row's
 * pool - the caller (the Lines tab's own Actions menu) already resolves every row's own
 * remaining / pool / stock-grid locations, since that resolution needs the same board
 * stock-detail read `OrderInquiryStockGrid` already makes.
 */
export interface ReserveRequestDialogRow {
  id: string;
  item_code: string | null;
  delivery_date: string | null;
  /** What is left to request on this row - the Requested input's own ceiling. */
  remaining: string;
  /** The pool warehouse id/code Requested defaults Location to. */
  defaultLocation: string;
  locationOptions: SearchableSelectOption[];
}

export function ReserveRequestDialog({
  open,
  onOpenChange,
  inquiryId,
  rows,
  onSent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  inquiryId: string;
  rows: ReserveRequestDialogRow[];
  onSent?: () => void;
}) {
  const [requested, setRequested] = React.useState<Record<string, number>>({});
  const [location, setLocation] = React.useState<Record<string, string>>({});
  const [note, setNote] = React.useState('');
  const [sending, setSending] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setRequested(
      Object.fromEntries(rows.map((row) => [row.id, Number(row.remaining || '0')])),
    );
    setLocation(Object.fromEntries(rows.map((row) => [row.id, row.defaultLocation])));
    setNote('');
  }, [open, rows]);

  async function handleSend() {
    setSending(true);
    try {
      const response = await createOrderInquiryReserveRequest(inquiryId, {
        rows: rows.map((row) => ({
          row_id: row.id,
          qty_requested: requested[row.id] ?? Number(row.remaining || '0'),
          warehouse_id: location[row.id] ?? row.defaultLocation,
        })),
        note: note.trim() ? note.trim() : null,
      });
      toast.success(
        `Request #${response.ordinal} sent to ${response.first_to_name ?? 'CS'}`,
      );
      onOpenChange(false);
      onSent?.();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to send that reserve request',
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Request CS to reserve</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex-1 space-y-4 overflow-y-auto">
          {rows.map((row) => {
            const remainingQty = Number(row.remaining || '0');
            return (
              <div key={row.id} className="space-y-3 rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">{row.item_code}</span>
                  <span className="text-xs text-muted-foreground">
                    {row.delivery_date ? `Due ${row.delivery_date}` : 'No delivery date'}
                    {' - '}remaining {row.remaining}
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor={`reserve-requested-${row.id}`}>Requested</Label>
                    <Input
                      id={`reserve-requested-${row.id}`}
                      type="number"
                      min={1}
                      max={remainingQty}
                      value={requested[row.id] ?? remainingQty}
                      onChange={(event) => {
                        const raw = Number(event.target.value);
                        const capped = Math.min(Math.max(raw || 0, 0), remainingQty);
                        setRequested((prev) => ({ ...prev, [row.id]: capped }));
                      }}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`reserve-location-${row.id}`}>Location</Label>
                    <SearchableSelect
                      id={`reserve-location-${row.id}`}
                      value={location[row.id] ?? row.defaultLocation}
                      onChange={(value) =>
                        setLocation((prev) => ({ ...prev, [row.id]: value }))
                      }
                      options={row.locationOptions}
                    />
                  </div>
                </div>
              </div>
            );
          })}
          <div className="space-y-1">
            <Label htmlFor="reserve-request-note">Note (optional)</Label>
            <Textarea
              id="reserve-request-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={2}
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>
            Cancel
          </Button>
          <Button onClick={handleSend} disabled={sending || rows.length === 0}>
            Send request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveRequestDialog;
