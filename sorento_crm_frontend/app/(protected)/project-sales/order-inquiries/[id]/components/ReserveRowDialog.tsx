'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { formatDateTime } from '@/lib/helpers';
import {
  reserveOrderInquiryRow,
  unreserveOrderInquiryRow,
} from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2/F3/F4/F5 - ONE dialog per Lines-grid
 * row, opened from the Reserve icon-button (`orderInquiryHeaderLinesColumns.tsx`).
 * Replaces round 1's `ReserveRequestsCard`/`ReserveRequestsSection` (the open-request
 * card above the grid): the Reserve tab is that card's own act-mode form, narrowed to
 * one row; the History tab (F3) is new.
 *
 * Kept free of `QueryClientProvider`/react-query entirely on purpose, the same reason
 * `ReserveRequestsCard` was: its own vitest suite renders it with no providers at all.
 * Every read this dialog needs (`openRequest`, `history`, the pool options) is resolved
 * by the CALLER and handed down as props; the two writes go straight to the feature
 * service, exactly as `ReserveRequestDialog` (the CREATE dialog next door) does.
 */

export interface ReserveRowDialogOpenRequest {
  requestId: string;
  ordinal: number;
  qtyRequested: string;
  requestedByName: string | null;
  requestedAt: string | null;
}

export interface ReserveRowDialogHistoryEntry {
  kind: 'requested' | 'reserved' | 'unreserved' | 'cancelled' | string;
  qty: string | null;
  location: string | null;
  reason: string | null;
  actorName: string | null;
  createdAt: string | null;
}

export interface ReserveRowDialogCancelControl {
  isPending: boolean;
  isBlocked: boolean;
  countdown: React.ReactNode;
  start: () => void;
}

const HISTORY_KIND_LABEL: Record<string, string> = {
  requested: 'Requested',
  reserved: 'Reserved',
  unreserved: 'Unreserved',
  cancelled: 'Request cancelled',
};

export function ReserveRowDialog({
  open,
  onOpenChange,
  rowId,
  itemCode,
  openRequest,
  history,
  locationOptions,
  defaultLocationId,
  availableQtyByLocation,
  netReservedQty,
  canAct,
  onConfirmed,
  onUnreserved,
  lastRequestId,
  cancelControl,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rowId: string;
  itemCode: string | null;
  /** The row's own OPEN (unanswered) request row - null once it has been answered
   * (or none was ever raised). Reserve/Reason inputs render only while this is set. */
  openRequest: ReserveRowDialogOpenRequest | null;
  /** Newest first (F3) - already resolved by the caller. */
  history: ReserveRowDialogHistoryEntry[];
  /** F1: every active pool for this row's own product, `<code>  available N`. */
  locationOptions: SearchableSelectOption[];
  defaultLocationId: string | null;
  availableQtyByLocation: Record<string, number>;
  /** The row's own NET reserved (sum reserved - sum unreserved) - read straight off
   * the worklist row (`reserved_qty`), never recomputed here. */
  netReservedQty: string;
  canAct: boolean;
  onConfirmed?: () => void;
  onUnreserved?: () => void;
  /** The request `openRequest` belongs to when it is open; the request that last
   * reserved this row when it is not (needed for Unreserve / History either way -
   * `openRequest` alone is null exactly when this dialog most needs it). */
  lastRequestId?: string | null;
  /** F2 header "Cancel request" - optional, absent renders nothing (plan 6c). */
  cancelControl?: ReserveRowDialogCancelControl | null;
}) {
  const requestedQty = openRequest ? Number(openRequest.qtyRequested || '0') : 0;
  const netReserved = Number(netReservedQty || '0');
  const effectiveRequestId = openRequest?.requestId ?? lastRequestId ?? '';

  const [location, setLocation] = React.useState('');
  const [reserved, setReserved] = React.useState(0);
  const [editedReserved, setEditedReserved] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);

  const [unreserveOpen, setUnreserveOpen] = React.useState(false);
  const [unreserveQty, setUnreserveQty] = React.useState('');
  const [unreserveNote, setUnreserveNote] = React.useState('');
  const [unreserving, setUnreserving] = React.useState(false);

  // AC-RS-28 (ported): reset only when the CALLER'S OWN resolved defaults actually
  // change - a value-identical re-render (a refetch landing the same server data)
  // must not wipe an in-progress edit.
  const openRequestSignature = openRequest
    ? `${openRequest.requestId}:${openRequest.qtyRequested}`
    : 'none';
  const optionsSignature = `${defaultLocationId ?? ''}|${locationOptions.map((o) => o.value).join(',')}`;
  React.useEffect(() => {
    if (!openRequest) return;
    const initialLocation = defaultLocationId ?? locationOptions[0]?.value ?? '';
    setLocation(initialLocation);
    const available = availableQtyByLocation[initialLocation];
    setReserved(Math.max(0, Math.min(requestedQty, available != null ? available : requestedQty)));
    setReason('');
    setEditedReserved(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequestSignature, optionsSignature]);

  function handleLocationChange(value: string) {
    setLocation(value);
    // AC-RS-55: Reserved recomputes from the NEW location's own availability, but
    // only while the reader has not touched Reserved yet - an edit they made stands.
    if (!editedReserved) {
      const available = availableQtyByLocation[value];
      setReserved(Math.max(0, Math.min(requestedQty, available != null ? available : requestedQty)));
    }
  }

  function handleReservedChange(event: React.ChangeEvent<HTMLInputElement>) {
    const raw = Number(event.target.value);
    setEditedReserved(true);
    setReserved(Math.min(Math.max(raw || 0, 0), requestedQty));
  }

  const short = reserved < requestedQty;
  const canConfirm = !short || reason.trim().length > 0;

  async function handleConfirm() {
    if (!openRequest) return;
    setConfirming(true);
    try {
      await reserveOrderInquiryRow(openRequest.requestId, rowId, {
        warehouse_id: location,
        qty_reserved: reserved,
        reason: reason.trim() ? reason.trim() : null,
      });
      toast.success('Reserved');
      onConfirmed?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to confirm the reserve');
    } finally {
      setConfirming(false);
    }
  }

  async function handleUnreserveConfirm() {
    setUnreserving(true);
    try {
      await unreserveOrderInquiryRow(effectiveRequestId, rowId, {
        qty: unreserveQty,
        note: unreserveNote.trim() ? unreserveNote.trim() : null,
      });
      toast.success('Unreserved');
      setUnreserveOpen(false);
      setUnreserveQty('');
      setUnreserveNote('');
      onUnreserved?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to unreserve');
    } finally {
      setUnreserving(false);
    }
  }

  // N-3 (ported, no UUID in the frontend UI): once a row is reserved with no open
  // request, `locationOptions`/`defaultLocationId` may carry nothing at all (the
  // server found no pool matching the warehouse actually chosen) - the read-only
  // location reads the History tab's own most recent `reserved` entry instead, which
  // is always a CODE, never a raw id.
  const lastReservedEntry = history.find((entry) => entry.kind === 'reserved');
  const showUnreserveOffer = !openRequest && netReserved > 0 && canAct;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <DialogTitle>Reserve{itemCode ? ` - ${itemCode}` : ''}</DialogTitle>
          {cancelControl && openRequest ? (
            cancelControl.countdown ?? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={cancelControl.isPending || cancelControl.isBlocked}
                onClick={() => cancelControl.start()}
              >
                Cancel request
              </Button>
            )
          ) : null}
        </DialogHeader>
        <DialogBody>
          <Tabs defaultValue="reserve" className="w-full">
            <TabsList variant="line" className="mb-3 w-full justify-start">
              <TabsTrigger value="reserve">Reserve</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>

            <TabsContent value="reserve" className="mt-0 focus-visible:outline-none">
              {openRequest ? (
                <div className="space-y-3">
                  <div className="text-sm text-muted-foreground">
                    Request #{openRequest.ordinal} - requested {openRequest.qtyRequested}
                    {openRequest.requestedByName ? ` by ${openRequest.requestedByName}` : ''}
                    {openRequest.requestedAt ? ` on ${formatDateTime(openRequest.requestedAt)}` : ''}
                  </div>
                  {canAct ? (
                    <>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div className="space-y-1">
                          <Label htmlFor="reserve-row-location">Location</Label>
                          <SearchableSelect
                            id="reserve-row-location"
                            value={location}
                            onChange={handleLocationChange}
                            options={locationOptions}
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="reserve-row-qty">Reserved</Label>
                          <Input
                            id="reserve-row-qty"
                            type="number"
                            min={0}
                            max={requestedQty}
                            value={reserved}
                            onChange={handleReservedChange}
                          />
                        </div>
                      </div>
                      {short ? (
                        <div className="space-y-1">
                          <Label htmlFor="reserve-row-reason">Reason</Label>
                          <Input
                            id="reserve-row-reason"
                            value={reason}
                            onChange={(event) => setReason(event.target.value)}
                          />
                        </div>
                      ) : null}
                      <div className="flex justify-end">
                        <Button onClick={handleConfirm} disabled={!canConfirm || confirming}>
                          Confirm reserved
                        </Button>
                      </div>
                    </>
                  ) : null}
                </div>
              ) : netReserved > 0 ? (
                <div className="space-y-3">
                  <div className="text-sm">
                    Reserved {netReservedQty}
                    {lastReservedEntry?.location ? ` @ ${lastReservedEntry.location}` : ''}
                  </div>
                  {showUnreserveOffer ? (
                    unreserveOpen ? (
                      <div className="space-y-2 rounded-lg border border-border p-3">
                        <div className="space-y-1">
                          <Label htmlFor="reserve-row-unreserve-qty">Qty</Label>
                          <Input
                            id="reserve-row-unreserve-qty"
                            type="number"
                            min={1}
                            max={netReserved}
                            value={unreserveQty}
                            onChange={(event) => setUnreserveQty(event.target.value)}
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="reserve-row-unreserve-note">Note</Label>
                          <Input
                            id="reserve-row-unreserve-note"
                            value={unreserveNote}
                            onChange={(event) => setUnreserveNote(event.target.value)}
                          />
                        </div>
                        <div className="flex justify-end gap-2">
                          <Button type="button" variant="outline" onClick={() => setUnreserveOpen(false)}>
                            Cancel
                          </Button>
                          <Button
                            onClick={handleUnreserveConfirm}
                            disabled={unreserving || !unreserveQty}
                          >
                            Confirm
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Button type="button" variant="outline" onClick={() => setUnreserveOpen(true)}>
                        Unreserve
                      </Button>
                    )
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing reserved on this row.</p>
              )}
            </TabsContent>

            <TabsContent value="history" className="mt-0 focus-visible:outline-none">
              <div className="space-y-2">
                {history.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No history yet.</p>
                ) : (
                  history.map((entry, index) => (
                    <div key={index} className="rounded-md border border-border p-2 text-xs">
                      <div className="font-medium">
                        {HISTORY_KIND_LABEL[entry.kind] ?? entry.kind}
                        {entry.qty ? ` ${entry.qty}` : ''}
                        {entry.location ? ` @ ${entry.location}` : ''}
                      </div>
                      <div className="text-muted-foreground">
                        {entry.actorName ?? 'Unknown'}
                        {entry.createdAt ? ` on ${formatDateTime(entry.createdAt)}` : ''}
                        {entry.reason ? ` - ${entry.reason}` : ''}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </TabsContent>
          </Tabs>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveRowDialog;
