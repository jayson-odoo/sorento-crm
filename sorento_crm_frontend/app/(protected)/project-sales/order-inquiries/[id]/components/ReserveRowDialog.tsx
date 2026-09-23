'use client';

import * as React from 'react';
import { Check } from 'lucide-react';
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
import type {
  OrderInquiryReserveRequestRow,
  ReserveRowPayload,
} from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2/F3/F4/F5 - ONE dialog per Lines-grid
 * row, opened from the Reserve icon-button (`orderInquiryHeaderLinesColumns.tsx`).
 * Replaces round 1's `ReserveRequestsCard`/`ReserveRequestsSection` (the open-request
 * card above the grid): the Reserve tab is that card's own act-mode form, narrowed to
 * one row; the History tab (F3) is new.
 *
 * Round 3 (section 6d G1, AC-RS-65..67): the email deep link (`?reserve=<request_id>`)
 * used to open this dialog for ONE row - the request's own first open row - and now
 * opens EVERY still-open row of that request at once, one section each with its own
 * Confirm reserved, no History tab (history lives on the line). `rows: ReserveRowDialogRow[]`
 * is the new, primary shape (length 1..N); the OLD scalar `rowId`/`itemCode`/
 * `openRequest`/`history`/`netReservedQty` props stay as a fallback for the single-row,
 * line-click path, which keeps its own Reserve/History tabs exactly as before -
 * `rows` with one entry renders identically, whichever way the caller reaches it.
 *
 * Kept free of `QueryClientProvider`/react-query entirely on purpose, the same reason
 * `ReserveRequestsCard` was: its own vitest suite renders it with no providers at all.
 * Every read this dialog needs (`openRequest`, `history`, the pool options) is resolved
 * by the CALLER and handed down as props. S5 (reviewer round): the two writes no
 * longer call the feature service directly either - `onReserve` is the caller's own
 * `useReserveOrderInquiryRow` mutation (`_shared/hooks/useOrderInquiry.ts`), and
 * `unreserveControl` (S2) is a server-deferred pending action
 * (`useDeferredAction`/`order_inquiry_reserve_row.unreserve`) the caller builds and
 * hands down the same way `cancelControl` already works.
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

/** Round 3 (AC-RS-65/AC-RS-66): one entry per row the dialog carries a section for. */
export interface ReserveRowDialogRow {
  rowId: string;
  itemCode: string | null;
  /** The row's own OPEN (unanswered) request row - null once it has been answered
   * (or none was ever raised). Reserve/Reason inputs render only while this is set. */
  openRequest: ReserveRowDialogOpenRequest | null;
  /** Newest first (F3) - already resolved by the caller. */
  history: ReserveRowDialogHistoryEntry[];
  /** The row's own NET reserved (sum reserved - sum unreserved) - read straight off
   * the worklist row (`reserved_qty`), never recomputed here. */
  netReservedQty: string;
}

export interface ReserveRowDialogCancelControl {
  isPending: boolean;
  isBlocked: boolean;
  countdown: React.ReactNode;
  start: () => void;
}

/**
 * S2 (ADR-PRODUCT-STANDARDS D7): Unreserve is a server-deferred pending action, not an
 * immediate write - `start` parks it and `countdown` (once non-null) replaces the
 * qty/note form with the SAME countdown + Cancel shape `cancelControl` already renders
 * in the header. There is no separate "confirm" step and no Escape handler here:
 * `DeferredCountdown` (`components/common/DeferredActionButton.tsx`) owns both already.
 */
export interface ReserveRowDialogUnreserveControl {
  isPending: boolean;
  isBlocked: boolean;
  countdown: React.ReactNode;
  start: (payload: { qty: string; note: string | null }) => void;
}

const HISTORY_KIND_LABEL: Record<string, string> = {
  requested: 'Requested',
  reserved: 'Reserved',
  unreserved: 'Unreserved',
  cancelled: 'Request cancelled',
};

function HistoryPanel({ history }: { history: ReserveRowDialogHistoryEntry[] }) {
  return (
    <div className="space-y-2">
      {history.length === 0 ? (
        <p className="text-sm text-muted-foreground">No history yet.</p>
      ) : (
        history.map((entry, index) => (
          // N4 (reviewer round): the entry's own identity - kind + when it
          // happened - never the array index, which reorders on refetch.
          <div
            key={`${entry.kind}-${entry.createdAt ?? index}`}
            className="rounded-md border border-border p-2 text-xs"
          >
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
  );
}

/** ONE row's own Reserve form - the per-row state this dialog used to hold at its top
 * level, now scoped to whichever row's section it belongs to (each section is its own
 * component instance, so React hooks per row work naturally). */
function ReserveRowSection({
  row,
  locationOptions,
  defaultLocationId,
  availableQtyByLocation,
  canAct,
  onReserve,
  onRowConfirmed,
  unreserveControl,
}: {
  row: ReserveRowDialogRow;
  locationOptions: SearchableSelectOption[];
  defaultLocationId: string | null;
  availableQtyByLocation: Record<string, number>;
  canAct: boolean;
  onReserve: (
    requestId: string,
    rowId: string,
    payload: ReserveRowPayload,
  ) => Promise<OrderInquiryReserveRequestRow>;
  /** Round 3: replaces the old top-level `onConfirmed` - names WHICH row confirmed and
   * with what qty, so a multi-row dialog can flip that one section read-only. */
  onRowConfirmed: (rowId: string, qty: number) => void;
  /** Absent in the multi-row (email-link) path: every row it carries is still open by
   * construction (`OrderInquiryDetail`'s own filter), so the "already reserved, offer
   * Unreserve" branch below never renders there in practice. */
  unreserveControl?: ReserveRowDialogUnreserveControl | null;
}) {
  const { rowId, openRequest, history, netReservedQty } = row;
  const requestedQty = openRequest ? Number(openRequest.qtyRequested || '0') : 0;
  const netReserved = Number(netReservedQty || '0');

  const [location, setLocation] = React.useState('');
  const [reserved, setReserved] = React.useState(0);
  const [editedReserved, setEditedReserved] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);

  const [unreserveOpen, setUnreserveOpen] = React.useState(false);
  const [unreserveQty, setUnreserveQty] = React.useState('');
  const [unreserveNote, setUnreserveNote] = React.useState('');

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

  // N2 (reviewer round): once the deferred action starts (`unreserveControl.start`
  // parked it, the countdown appears), the qty/note form must not sit around
  // holding what was typed - a later render finding `netReserved` already smaller
  // (the countdown committed) would otherwise reopen the SAME form pre-filled
  // above the new net. Keyed on the boolean, not the `ReactNode` itself: `countdown`
  // is a fresh element on every render, which would fire this every time instead
  // of only on the false -> true transition.
  const unreserveCountdownActive = Boolean(unreserveControl?.countdown);
  React.useEffect(() => {
    if (!unreserveCountdownActive) return;
    setUnreserveOpen(false);
    setUnreserveQty('');
    setUnreserveNote('');
  }, [unreserveCountdownActive]);

  const short = reserved < requestedQty;
  const canConfirm = !short || reason.trim().length > 0;

  // Gap fix (round 2 browser evidence, postfix-linescope-above-net-silent.png): a
  // qty above the row's own net reserved (or 0/blank) used to reach `unreserveControl
  // .start` unchecked - the deferred action parked, the countdown ran, and the server
  // refused it at commit with the named limit. Checked here instead, before the park
  // ever happens, so a bad value never leaves the reader waiting out a window for a
  // refusal the form could have named immediately.
  const unreserveQtyNumber = Number(unreserveQty);
  const unreserveQtyAboveNet =
    unreserveQty.trim() !== '' && Number.isFinite(unreserveQtyNumber) && unreserveQtyNumber > netReserved;
  const unreserveQtyInvalid =
    unreserveQty.trim() === '' ||
    !Number.isFinite(unreserveQtyNumber) ||
    unreserveQtyNumber < 1 ||
    unreserveQtyNumber > netReserved;

  async function handleConfirm() {
    if (!openRequest) return;
    setConfirming(true);
    try {
      await onReserve(openRequest.requestId, rowId, {
        warehouse_id: location,
        qty_reserved: reserved,
        reason: reason.trim() ? reason.trim() : null,
      });
      onRowConfirmed(rowId, reserved);
    } catch {
      // The caller's own mutation hook already toasted the error (S5).
    } finally {
      setConfirming(false);
    }
  }

  // S2: starts the deferred action - no confirm step here, the button BECOMES the
  // countdown (rendered below, replacing this form) the instant `start` parks it.
  function handleUnreserveStart() {
    unreserveControl?.start({
      qty: unreserveQty,
      note: unreserveNote.trim() ? unreserveNote.trim() : null,
    });
  }

  // N-3 (ported, no UUID in the frontend UI): once a row is reserved with no open
  // request, `locationOptions`/`defaultLocationId` may carry nothing at all (the
  // server found no pool matching the warehouse actually chosen) - the read-only
  // location reads the History tab's own most recent `reserved` entry instead, which
  // is always a CODE, never a raw id.
  const lastReservedEntry = history.find((entry) => entry.kind === 'reserved');
  const showUnreserveOffer = !openRequest && netReserved > 0 && canAct;

  if (!openRequest) {
    return netReserved > 0 ? (
      <div className="space-y-3">
        <div className="text-sm">
          Reserved {netReservedQty}
          {lastReservedEntry?.location ? ` @ ${lastReservedEntry.location}` : ''}
        </div>
        {showUnreserveOffer && unreserveControl?.countdown ? (
          // S2: the SAME countdown shape `cancelControl` renders in the
          // header - no confirm step, Escape does not cancel it
          // (`DeferredCountdown` owns both already), and the server
          // commits even if this dialog closes mid-window.
          unreserveControl.countdown
        ) : showUnreserveOffer ? (
          unreserveOpen ? (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <div className="space-y-1">
                <Label htmlFor={`reserve-row-unreserve-qty-${rowId}`}>Qty</Label>
                <Input
                  id={`reserve-row-unreserve-qty-${rowId}`}
                  type="number"
                  min={1}
                  max={netReserved}
                  step="any"
                  value={unreserveQty}
                  onChange={(event) => setUnreserveQty(event.target.value)}
                />
                {unreserveQtyAboveNet ? (
                  <p className="text-xs text-destructive">
                    Up to {netReservedQty} can be released
                  </p>
                ) : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor={`reserve-row-unreserve-note-${rowId}`}>Note</Label>
                <Input
                  id={`reserve-row-unreserve-note-${rowId}`}
                  value={unreserveNote}
                  onChange={(event) => setUnreserveNote(event.target.value)}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setUnreserveOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleUnreserveStart}
                  disabled={
                    !unreserveControl ||
                    unreserveControl.isPending ||
                    unreserveControl.isBlocked ||
                    unreserveQtyInvalid
                  }
                >
                  Unreserve
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
    );
  }

  return (
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
              <Label htmlFor={`reserve-row-location-${rowId}`}>Location</Label>
              <SearchableSelect
                id={`reserve-row-location-${rowId}`}
                value={location}
                onChange={handleLocationChange}
                options={locationOptions}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor={`reserve-row-qty-${rowId}`}>Reserved</Label>
              <Input
                id={`reserve-row-qty-${rowId}`}
                type="number"
                min={0}
                max={requestedQty}
                step="any"
                value={reserved}
                onChange={handleReservedChange}
              />
            </div>
          </div>
          {short ? (
            <div className="space-y-1">
              <Label htmlFor={`reserve-row-reason-${rowId}`}>Reason</Label>
              <Input
                id={`reserve-row-reason-${rowId}`}
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
  );
}

export function ReserveRowDialog({
  open,
  onOpenChange,
  rows,
  rowId,
  itemCode,
  openRequest,
  history,
  locationOptions,
  defaultLocationId,
  availableQtyByLocation,
  netReservedQty,
  canAct,
  onReserve,
  onConfirmed,
  unreserveControl,
  cancelControl,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Round 3 (AC-RS-65/AC-RS-66): the primary shape, one section per row, length 1..N.
   * A length of 1 renders exactly like the old single-row dialog (Reserve/History
   * tabs); more than one drops the History tab (history lives on the line) and closes
   * itself once the last open section confirms. */
  rows?: ReserveRowDialogRow[];
  /** Single-row fallback (the line-click path), kept for a caller that has not moved
   * to `rows` - functionally identical to `rows: [{ rowId, itemCode, openRequest,
   * history, netReservedQty }]`. */
  rowId?: string;
  itemCode?: string | null;
  openRequest?: ReserveRowDialogOpenRequest | null;
  /** Newest first (F3) - already resolved by the caller. */
  history?: ReserveRowDialogHistoryEntry[];
  /** F1: every active pool for this row's own product, `<code>  available N`. */
  locationOptions: SearchableSelectOption[];
  defaultLocationId: string | null;
  availableQtyByLocation: Record<string, number>;
  /** The row's own NET reserved (sum reserved - sum unreserved) - read straight off
   * the worklist row (`reserved_qty`), never recomputed here. */
  netReservedQty?: string;
  canAct: boolean;
  /** S5: the caller's own `useReserveOrderInquiryRow` mutation. */
  onReserve: (
    requestId: string,
    rowId: string,
    payload: ReserveRowPayload,
  ) => Promise<OrderInquiryReserveRequestRow>;
  onConfirmed?: () => void;
  /** S2: null while nothing offers Unreserve yet (canAct false, or nothing reserved).
   * Only meaningful on the single-row path - a multi-row (email-link) dialog carries
   * only still-open rows, which never offer Unreserve. */
  unreserveControl?: ReserveRowDialogUnreserveControl | null;
  /** Header "Cancel request" (plan 6c/6d) - applies to the WHOLE request, so it
   * renders whenever ANY row this dialog carries still has an open request answer. */
  cancelControl?: ReserveRowDialogCancelControl | null;
}) {
  const effectiveRows: ReserveRowDialogRow[] = React.useMemo(() => {
    if (rows && rows.length > 0) return rows;
    if (rowId) {
      return [
        {
          rowId,
          itemCode: itemCode ?? null,
          openRequest: openRequest ?? null,
          history: history ?? [],
          netReservedQty: netReservedQty ?? '0',
        },
      ];
    }
    return [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, rowId, itemCode, openRequest, history, netReservedQty]);

  const showTabs = effectiveRows.length === 1;
  const anyOpenRequest = effectiveRows.some((row) => Boolean(row.openRequest));

  // Round 3: which rows this dialog session has already confirmed, and with what qty -
  // flips that row's own section to a read-only "Reserved N" line, and closes the
  // dialog once every open row has one.
  const [confirmedRows, setConfirmedRows] = React.useState<Record<string, number>>({});
  const rowsSignature = effectiveRows.map((row) => row.rowId).join(',');
  React.useEffect(() => {
    setConfirmedRows({});
  }, [rowsSignature]);

  function handleRowConfirmed(confirmedRowId: string, qty: number) {
    setConfirmedRows((prev) => {
      const next = { ...prev, [confirmedRowId]: qty };
      // Multi-row only: the tabs (single-row) path keeps the dialog open after a
      // Confirm, exactly as it always has.
      if (!showTabs && Object.keys(next).length >= effectiveRows.length) {
        onOpenChange(false);
      }
      return next;
    });
    onConfirmed?.();
  }

  const soleRow = effectiveRows[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <DialogTitle>
            Reserve{showTabs && soleRow?.itemCode ? ` - ${soleRow.itemCode}` : ''}
          </DialogTitle>
          {cancelControl && anyOpenRequest ? (
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
          {showTabs ? (
            <Tabs defaultValue="reserve" className="w-full">
              <TabsList variant="line" className="mb-3 w-full justify-start">
                <TabsTrigger value="reserve">Reserve</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>

              <TabsContent value="reserve" className="mt-0 focus-visible:outline-none">
                {soleRow ? (
                  <ReserveRowSection
                    row={soleRow}
                    locationOptions={locationOptions}
                    defaultLocationId={defaultLocationId}
                    availableQtyByLocation={availableQtyByLocation}
                    canAct={canAct}
                    onReserve={onReserve}
                    onRowConfirmed={handleRowConfirmed}
                    unreserveControl={unreserveControl}
                  />
                ) : null}
              </TabsContent>

              <TabsContent value="history" className="mt-0 focus-visible:outline-none">
                <HistoryPanel history={soleRow?.history ?? []} />
              </TabsContent>
            </Tabs>
          ) : (
            // Round 3 (AC-RS-65/AC-RS-66): no tabs - one section per row, each with its
            // own item-code heading and its own Confirm reserved. History does not
            // render here; it lives on the line (single-row path above).
            <div className="space-y-4">
              {effectiveRows.map((row) => {
                const confirmedQty = confirmedRows[row.rowId];
                if (confirmedQty != null) {
                  return (
                    <div
                      key={row.rowId}
                      className="flex items-center gap-2 rounded-lg border border-border p-3"
                    >
                      <Check className="size-4 text-emerald-600" aria-hidden />
                      <span className="text-sm font-medium">{row.itemCode}</span>
                      <span className="text-sm text-muted-foreground">
                        Reserved {confirmedQty}
                      </span>
                    </div>
                  );
                }
                return (
                  <div key={row.rowId} className="space-y-2 rounded-lg border border-border p-3">
                    <div className="text-sm font-medium">{row.itemCode}</div>
                    <ReserveRowSection
                      row={row}
                      locationOptions={locationOptions}
                      defaultLocationId={defaultLocationId}
                      availableQtyByLocation={availableQtyByLocation}
                      canAct={canAct}
                      onReserve={onReserve}
                      onRowConfirmed={handleRowConfirmed}
                      unreserveControl={undefined}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveRowDialog;
