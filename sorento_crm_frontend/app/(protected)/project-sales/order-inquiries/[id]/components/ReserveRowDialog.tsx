'use client';

import * as React from 'react';
import { type ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
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
 * This component imports no feature service of its own - every read it needs
 * (`openRequest`, `history`, the pool options) is resolved by the CALLER and handed
 * down as props. S5 (reviewer round): the two writes no longer call the feature
 * service directly either - `onReserve` is the caller's own `useReserveOrderInquiryRow`
 * mutation (`_shared/hooks/useOrderInquiry.ts`), and `unreserveControl` (S2) is a
 * server-deferred pending action (`useDeferredAction`/`order_inquiry_reserve_row.
 * unreserve`) the caller builds and hands down the same way `cancelControl` already
 * works.
 *
 * G6 (round 3 fix round 3): the multi-row body is now a `DataGrid`
 * (`components/ui/data-grid`), which reads `useQueryClient()` internally
 * (`useListingColumnPreferences`, called unconditionally regardless of whether a
 * `listingKey` is passed) - so unlike before, this component's own vitest suite now
 * needs a `QueryClientProvider` ancestor. No `listingKey` is passed, so the hook's own
 * `useQuery` stays `enabled: false` and issues no network read.
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
  /** Fix round 1 (AC-RS-65b/AC-RS-66b): this row's OWN pool options/availability/
   * default - two rows in one multi-row dialog can name different products, and each
   * must see its own product's own pools. Absent falls back to the dialog's own
   * top-level `locationOptions`/`availableQtyByLocation`/`defaultLocationId` prop, so a
   * single-row caller (or an older caller that has not moved to per-row resolution)
   * renders exactly as before. */
  locationOptions?: SearchableSelectOption[];
  availableQtyByLocation?: Record<string, number>;
  defaultLocationId?: string | null;
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

/**
 * N1 (fix round 4 nit): a `SearchableSelect` option's own `label` carries the
 * available-qty suffix in production (`useReserveRowOptions.ts`: `${location}
 * available ${qty}`, two spaces), so reading the label straight as the "location"
 * the stale confirm echo names would flash "Reserved 12 @ BRW  available 87" - the
 * BARE code is everything before that double space (absent in test fixtures that
 * never carry the suffix, where this is a no-op split).
 */
function bareLocationCode(label: string): string {
  return label.split('  ')[0];
}

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
  showRequestLine = true,
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
  /** Round 3: replaces the old top-level `onConfirmed` - names WHICH row confirmed,
   * with what qty and at which location (R1, fix round 3: the CODE, resolved off
   * `locationOptions` - never the raw id `location` state holds), so a multi-row
   * dialog can flip that one section read-only with the same "Reserved N @ Location"
   * shape the real (props-caught-up) branch below renders. */
  onRowConfirmed: (rowId: string, qty: number, locationLabel: string) => void;
  /** Absent in the multi-row (email-link) path: every row it carries is still open by
   * construction (`OrderInquiryDetail`'s own filter), so the "already reserved, offer
   * Unreserve" branch below never renders there in practice. */
  unreserveControl?: ReserveRowDialogUnreserveControl | null;
  /** Nit (fix round 2): every row in a multi-row dialog shares ONE request, so the
   * "Request #N - requested N by X on <date>" line is redundant printed once per
   * section - the multi-row caller renders it ONCE in the dialog header instead and
   * passes `false` here; the single-row (tabs) path is unchanged (AC-RS-61). */
  showRequestLine?: boolean;
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
      // R1: the CODE, not the raw warehouse id `location` itself holds (no UUID in
      // the frontend UI) - the same resolution the real "already reserved" branch
      // below reads off `history`'s own most recent `reserved` entry. N1 (fix round
      // 4 nit): the option's own LABEL carries the available-qty suffix in
      // production - `bareLocationCode` strips it, so the flash never leaks it.
      const selectedOption = locationOptions.find((option) => option.value === location);
      const locationLabel = selectedOption ? bareLocationCode(selectedOption.label) : '';
      onRowConfirmed(rowId, reserved, locationLabel);
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
      {showRequestLine ? (
        <div className="text-sm text-muted-foreground">
          Request #{openRequest.ordinal} - requested {openRequest.qtyRequested}
          {openRequest.requestedByName ? ` by ${openRequest.requestedByName}` : ''}
          {openRequest.requestedAt ? ` on ${formatDateTime(openRequest.requestedAt)}` : ''}
        </div>
      ) : null}
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

/** Round 3 fix round 3 G6 (`PLAN-oi-request-cs-reserve.md` section 6d,
 * `oi-request-cs-reserve-acceptance-criteria.md` AC-RS-74): a multi-row dialog's own
 * per-row edit, held in the DIALOG rather than inside a mounted `ReserveRowSection` -
 * the grid renders every row as ONE DataGrid cell each, so there is no per-row React
 * component instance left to hold its own `useState` the way the stacked-cards layout
 * used to. Same reset rule `ReserveRowSection`'s own effect carried: a value-identical
 * re-render (a refetch landing the same server data) must not wipe an in-progress
 * edit - `signature` pins that. */
interface ReserveGridDraft {
  signature: string;
  location: string;
  reserved: number;
  editedReserved: boolean;
  reason: string;
}

function reserveGridDraftSignature(
  row: ReserveRowDialogRow,
  locationOptions: SearchableSelectOption[],
  defaultLocationId: string | null,
): string {
  if (!row.openRequest) return 'none';
  return `${row.openRequest.requestId}:${row.openRequest.qtyRequested}:${defaultLocationId ?? ''}:${locationOptions.map((o) => o.value).join(',')}`;
}

function reserveGridInitialDraft(
  row: ReserveRowDialogRow,
  locationOptions: SearchableSelectOption[],
  defaultLocationId: string | null,
  availableQtyByLocation: Record<string, number>,
): ReserveGridDraft | null {
  if (!row.openRequest) return null;
  const requestedQty = Number(row.openRequest.qtyRequested || '0');
  const initialLocation = defaultLocationId ?? locationOptions[0]?.value ?? '';
  const available = availableQtyByLocation[initialLocation];
  return {
    signature: reserveGridDraftSignature(row, locationOptions, defaultLocationId),
    location: initialLocation,
    reserved: Math.max(0, Math.min(requestedQty, available != null ? available : requestedQty)),
    editedReserved: false,
    reason: '',
  };
}

/**
 * G6: ONE DataGrid row per product, replacing the stacked `ReserveRowSection` cards
 * for a multi-row dialog (`effectiveRows.length > 1`). The single-row (tabs) path is
 * untouched - it keeps `ReserveRowSection` exactly as before.
 *
 * Every prop, callback, endpoint call and piece of session state the multi-row path
 * already carried stays: `confirmedRows`/`onRowConfirmed` (the dialog's own close
 * effect still watches it), the O3 "already confirmed this session" 4th arg to
 * `onReserve`, and N1's bare-location echo. `showRequestLine`'s old purpose - a
 * read-only viewer still sees what was requested - is now met unconditionally by the
 * always-visible Requested column rather than a conditional text line.
 */
function ReserveRowsGrid({
  rows,
  locationOptions,
  defaultLocationId,
  availableQtyByLocation,
  canAct,
  onReserve,
  handleReserve,
  confirmedRows,
  onRowConfirmed,
}: {
  rows: ReserveRowDialogRow[];
  locationOptions: SearchableSelectOption[];
  defaultLocationId: string | null;
  availableQtyByLocation: Record<string, number>;
  canAct: boolean;
  /** The RAW caller prop - `confirmAllGridRows` below builds its own 4th arg as it
   * walks the still-open rows in order, so it cannot go through `handleReserve`'s own
   * (single-call) wrapping. */
  onReserve: (
    requestId: string,
    rowId: string,
    payload: ReserveRowPayload,
    alreadyConfirmedRowIds?: string[],
  ) => Promise<OrderInquiryReserveRequestRow>;
  /** The dialog's own wrapper (O3) - used by the per-row Confirm reserved button,
   * exactly the calling convention `ReserveRowSection` already used. */
  handleReserve: (
    requestId: string,
    rowId: string,
    payload: ReserveRowPayload,
  ) => Promise<OrderInquiryReserveRequestRow>;
  confirmedRows: Record<string, { qty: number; location: string }>;
  onRowConfirmed: (rowId: string, qty: number, locationLabel: string) => void;
}) {
  const [drafts, setDrafts] = React.useState<Record<string, ReserveGridDraft>>({});
  const [confirmingRowId, setConfirmingRowId] = React.useState<string | null>(null);
  const [confirmingAll, setConfirmingAll] = React.useState(false);

  const draftsSignature = rows
    .map(
      (row) =>
        `${row.rowId}=${reserveGridDraftSignature(
          row,
          row.locationOptions ?? locationOptions,
          row.defaultLocationId ?? defaultLocationId,
        )}`,
    )
    .join('|');

  React.useEffect(() => {
    setDrafts((prev) => {
      const next: Record<string, ReserveGridDraft> = {};
      for (const row of rows) {
        if (!row.openRequest) continue;
        const rowLocationOptions = row.locationOptions ?? locationOptions;
        const rowDefaultLocationId = row.defaultLocationId ?? defaultLocationId;
        const rowAvailable = row.availableQtyByLocation ?? availableQtyByLocation;
        const signature = reserveGridDraftSignature(row, rowLocationOptions, rowDefaultLocationId);
        const existing = prev[row.rowId];
        next[row.rowId] =
          existing && existing.signature === signature
            ? existing
            : (reserveGridInitialDraft(row, rowLocationOptions, rowDefaultLocationId, rowAvailable) ??
              existing);
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftsSignature]);

  function handleLocationChange(row: ReserveRowDialogRow, value: string) {
    setDrafts((prev) => {
      const current = prev[row.rowId];
      if (!current || !row.openRequest) return prev;
      const requestedQty = Number(row.openRequest.qtyRequested || '0');
      const rowAvailable = row.availableQtyByLocation ?? availableQtyByLocation;
      const available = rowAvailable[value];
      const reserved = current.editedReserved
        ? current.reserved
        : Math.max(0, Math.min(requestedQty, available != null ? available : requestedQty));
      return { ...prev, [row.rowId]: { ...current, location: value, reserved } };
    });
  }

  function handleReservedChange(row: ReserveRowDialogRow, raw: number) {
    setDrafts((prev) => {
      const current = prev[row.rowId];
      if (!current || !row.openRequest) return prev;
      const requestedQty = Number(row.openRequest.qtyRequested || '0');
      return {
        ...prev,
        [row.rowId]: { ...current, editedReserved: true, reserved: Math.min(Math.max(raw || 0, 0), requestedQty) },
      };
    });
  }

  function handleReasonChange(row: ReserveRowDialogRow, value: string) {
    setDrafts((prev) => {
      const current = prev[row.rowId];
      if (!current) return prev;
      return { ...prev, [row.rowId]: { ...current, reason: value } };
    });
  }

  function locationLabelFor(row: ReserveRowDialogRow, value: string): string {
    const rowLocationOptions = row.locationOptions ?? locationOptions;
    const selectedOption = rowLocationOptions.find((option) => option.value === value);
    // N1 (fix round 4 nit, ported): the bare code, never the whole option label (which
    // may carry an " available N" suffix in production).
    return selectedOption ? bareLocationCode(selectedOption.label) : '';
  }

  async function confirmRow(row: ReserveRowDialogRow) {
    const draft = drafts[row.rowId];
    if (!row.openRequest || !draft) return;
    setConfirmingRowId(row.rowId);
    try {
      await handleReserve(row.openRequest.requestId, row.rowId, {
        warehouse_id: draft.location,
        qty_reserved: draft.reserved,
        reason: draft.reason.trim() ? draft.reason.trim() : null,
      });
      onRowConfirmed(row.rowId, draft.reserved, locationLabelFor(row, draft.location));
    } catch {
      // The caller's own mutation hook already toasted the error (S5).
    } finally {
      setConfirmingRowId((id) => (id === row.rowId ? null : id));
    }
  }

  /** Footer Confirm all (AC-RS-74): calls `onReserve` once per still-open row, IN
   * TABLE ORDER, awaiting each before the next - stopping at the first rejection so
   * every row confirmed before it stays confirmed (its own `onRowConfirmed` already
   * ran). The O3 4th arg is built by hand here (never through `handleReserve`, which
   * reads the dialog's own `confirmedRows` STATE - stale mid-loop, since a state
   * update from an earlier iteration has not necessarily re-rendered this component
   * by the time the next iteration's own call goes out). */
  async function confirmAll() {
    setConfirmingAll(true);
    const alreadyConfirmed = new Set(Object.keys(confirmedRows));
    try {
      for (const row of rows) {
        if (alreadyConfirmed.has(row.rowId)) continue;
        const draft = drafts[row.rowId];
        if (!row.openRequest || !draft) continue;
        try {
          await onReserve(
            row.openRequest.requestId,
            row.rowId,
            {
              warehouse_id: draft.location,
              qty_reserved: draft.reserved,
              reason: draft.reason.trim() ? draft.reason.trim() : null,
            },
            Array.from(alreadyConfirmed),
          );
          alreadyConfirmed.add(row.rowId);
          onRowConfirmed(row.rowId, draft.reserved, locationLabelFor(row, draft.location));
        } catch {
          break; // AC-RS-74: stop after a rejected call - earlier rows stay confirmed.
        }
      }
    } finally {
      setConfirmingAll(false);
    }
  }

  // G6: `columns` must stay REFERENTIALLY STABLE across a keystroke or a Confirm
  // click - `flexRender` renders a columnDef's own `cell` FUNCTION as the component
  // type, so a `columns` array recomputed every render hands each cell a brand new
  // function identity every time, which React reads as a brand new component type
  // and unmounts/remounts the `<Input>`/`<SearchableSelect>` underneath it - losing
  // focus and dropping the very keystroke that triggered the re-render (measured
  // live in a minimal repro: the DOM node before and after a `fireEvent.change` were
  // not `===`). `latestRef` carries every value and handler the (now permanently
  // memoized) cell closures need, refreshed on every render, so a keystroke's own
  // state update never reaches `columns` itself.
  const latestRef = React.useRef({
    confirmedRows,
    drafts,
    canAct,
    locationOptions,
    confirmingRowId,
    confirmingAll,
    handleLocationChange,
    handleReservedChange,
    handleReasonChange,
    confirmRow,
    confirmAll,
    locationLabelFor,
  });
  latestRef.current = {
    confirmedRows,
    drafts,
    canAct,
    locationOptions,
    confirmingRowId,
    confirmingAll,
    handleLocationChange,
    handleReservedChange,
    handleReasonChange,
    confirmRow,
    confirmAll,
    locationLabelFor,
  };

  const columns = React.useMemo<ColumnDef<ReserveRowDialogRow>[]>(
    () => [
      {
        id: 'product',
        header: 'Product',
        cell: ({ row }) => (
          <span className="block truncate text-sm font-medium" title={row.original.itemCode ?? undefined}>
            {row.original.itemCode}
          </span>
        ),
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'requested',
        header: 'Requested',
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.openRequest?.qtyRequested ?? '0'}</span>
        ),
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Requested', headerClassName: 'text-end', cellClassName: 'text-end' },
      },
      {
        id: 'location',
        header: 'Location',
        cell: ({ row }) => {
          const r = row.original;
          const { confirmedRows: confirmedNow, drafts: draftsNow, canAct: canActNow, locationOptions: locationOptionsNow } =
            latestRef.current;
          const confirmed = confirmedNow[r.rowId];
          const draft = draftsNow[r.rowId];
          if (confirmed) {
            return (
              <span className="block truncate text-sm text-muted-foreground">
                {confirmed.location}
              </span>
            );
          }
          if (!draft) return null;
          if (!canActNow) {
            return (
              <span className="block truncate text-sm">
                {latestRef.current.locationLabelFor(r, draft.location)}
              </span>
            );
          }
          return (
            <>
              <Label htmlFor={`reserve-grid-location-${r.rowId}`} className="sr-only">
                Location
              </Label>
              <SearchableSelect
                id={`reserve-grid-location-${r.rowId}`}
                value={draft.location}
                onChange={(value) => latestRef.current.handleLocationChange(r, value)}
                options={r.locationOptions ?? locationOptionsNow}
              />
            </>
          );
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'reserved',
        header: 'Reserved',
        cell: ({ row }) => {
          const r = row.original;
          const { confirmedRows: confirmedNow, drafts: draftsNow, canAct: canActNow } = latestRef.current;
          const confirmed = confirmedNow[r.rowId];
          const draft = draftsNow[r.rowId];
          if (confirmed) {
            return (
              <span className="flex items-center gap-1.5 text-sm">
                <Check className="size-4 text-emerald-600" aria-hidden />
                Reserved {confirmed.qty}
              </span>
            );
          }
          if (!draft) return null;
          const requestedQty = Number(r.openRequest?.qtyRequested || '0');
          if (!canActNow) {
            return <span className="tabular-nums">{draft.reserved}</span>;
          }
          return (
            <>
              <Label htmlFor={`reserve-grid-reserved-${r.rowId}`} className="sr-only">
                Reserved
              </Label>
              <Input
                id={`reserve-grid-reserved-${r.rowId}`}
                type="number"
                min={0}
                max={requestedQty}
                step="any"
                value={draft.reserved}
                onChange={(event) =>
                  latestRef.current.handleReservedChange(r, Number(event.target.value))
                }
              />
            </>
          );
        },
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Reserved' },
      },
      {
        id: 'reason',
        header: 'Reason',
        cell: ({ row }) => {
          const r = row.original;
          const { confirmedRows: confirmedNow, drafts: draftsNow, canAct: canActNow } = latestRef.current;
          const confirmed = confirmedNow[r.rowId];
          const draft = draftsNow[r.rowId];
          if (confirmed || !draft) return null;
          const requestedQty = Number(r.openRequest?.qtyRequested || '0');
          const short = draft.reserved < requestedQty;
          if (!short) return null;
          if (!canActNow) {
            return <span className="block truncate text-sm">{draft.reason || null}</span>;
          }
          return (
            <>
              <Label htmlFor={`reserve-grid-reason-${r.rowId}`} className="sr-only">
                Reason
              </Label>
              <Input
                id={`reserve-grid-reason-${r.rowId}`}
                value={draft.reason}
                onChange={(event) => latestRef.current.handleReasonChange(r, event.target.value)}
              />
            </>
          );
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Reason' },
      },
      // Always present (a fixed column COUNT keeps `columns` structurally stable
      // whether or not `canAct` is true right now) - empty when read-only.
      {
        id: 'action',
        header: '',
        cell: ({ row }) => {
          const r = row.original;
          const { confirmedRows: confirmedNow, drafts: draftsNow, canAct: canActNow, confirmingRowId: confirmingRowIdNow, confirmingAll: confirmingAllNow } =
            latestRef.current;
          if (!canActNow) return null;
          const confirmed = confirmedNow[r.rowId];
          const draft = draftsNow[r.rowId];
          if (confirmed || !draft) return null;
          const requestedQty = Number(r.openRequest?.qtyRequested || '0');
          const short = draft.reserved < requestedQty;
          const canConfirm = !short || draft.reason.trim().length > 0;
          return (
            <Button
              type="button"
              size="sm"
              onClick={() => latestRef.current.confirmRow(r)}
              disabled={!canConfirm || confirmingRowIdNow === r.rowId || confirmingAllNow}
            >
              Confirm reserved
            </Button>
          );
        },
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Action' },
      },
    ],
    // Deliberately empty: see the doc above - `latestRef` supplies every value and
    // handler these closures need, refreshed every render.
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.rowId,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const openRows = rows.filter((row) => confirmedRows[row.rowId] == null && row.openRequest);
  const confirmAllDisabled =
    !canAct ||
    confirmingAll ||
    openRows.length === 0 ||
    openRows.some((row) => {
      const draft = drafts[row.rowId];
      const requestedQty = Number(row.openRequest?.qtyRequested || '0');
      if (!draft) return true;
      return draft.reserved < requestedQty && draft.reason.trim().length === 0;
    });

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <DataGrid
          table={table}
          recordCount={rows.length}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <DataGridTable />
        </DataGrid>
      </div>
      {canAct ? (
        <div className="flex justify-end">
          <Button type="button" onClick={confirmAll} disabled={confirmAllDisabled}>
            Confirm all
          </Button>
        </div>
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
  /** S5: the caller's own `useReserveOrderInquiryRow` mutation. O3 (fix round 4
   * nit): the FOURTH arg names every row THIS dialog session has already confirmed
   * (`Object.keys(confirmedRows)` at the moment of the call, threaded in by this
   * component itself below - never a `ReserveRowSection` concern) - the caller's own
   * `reserveRequestsQuery.data` can still read a row this session just answered as
   * open (the refetch it triggered has not landed yet), and a fast second confirm
   * needs to know that row is DONE regardless of what the stale cache still says. */
  onReserve: (
    requestId: string,
    rowId: string,
    payload: ReserveRowPayload,
    alreadyConfirmedRowIds?: string[],
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
  }, [rows, rowId, itemCode, openRequest, history, netReservedQty]);

  const showTabs = effectiveRows.length === 1;
  const anyOpenRequest = effectiveRows.some((row) => Boolean(row.openRequest));

  // Round 3: which rows this dialog session has already confirmed, and with what qty
  // + location - flips that row's own section to a read-only "Reserved N @ Location"
  // line, and closes the dialog once every open row has one.
  const [confirmedRows, setConfirmedRows] = React.useState<
    Record<string, { qty: number; location: string }>
  >({});
  const rowsSignature = effectiveRows.map((row) => row.rowId).join(',');
  React.useEffect(() => {
    setConfirmedRows({});
  }, [rowsSignature]);

  // R2 (fix round 3 review finding): the next state is computed via the FUNCTIONAL
  // updater form, never off the `confirmedRows` closure - two sections' own
  // `handleConfirm` resolving close enough together that React batches the
  // resulting state updates both read the SAME stale closure under the old
  // plain-object form, and the second silently overwrote the first's flip.
  // `onOpenChange` never runs from inside the updater (React may invoke it more
  // than once) - the close decision moves to its own effect below.
  function handleRowConfirmed(confirmedRowId: string, qty: number, locationLabel: string) {
    setConfirmedRows((prev) => ({ ...prev, [confirmedRowId]: { qty, location: locationLabel } }));
    onConfirmed?.();
  }

  // O1 (fix round 4 nit): reads `confirmedRows` STATE directly - the functional
  // updater above already guarantees it is fully merged by the time this effect
  // runs (React applies queued updaters in order off the true previous state, never
  // a stale closure, however many land in the same batch), so a separate ref
  // mirroring the same count was redundant. Multi-row only (the tabs/single-row
  // path keeps the dialog open after a Confirm, exactly as it always has).
  React.useEffect(() => {
    if (showTabs) return;
    if (effectiveRows.length === 0) return;
    if (Object.keys(confirmedRows).length >= effectiveRows.length) {
      onOpenChange(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmedRows]);

  // O3 (fix round 4 nit): wraps the CALLER's own `onReserve` with the row ids THIS
  // dialog session has already confirmed, read fresh off `confirmedRows` on every
  // render (never stale) - a fast second confirm's own `onReserve` call needs to
  // know its SIBLING section already answered even though the caller's own read
  // query has not refetched yet. `ReserveRowSection` itself is untouched: it still
  // calls a 3-arg `onReserve`, this wrapping happens only here.
  const handleReserve = React.useCallback(
    (requestId: string, rowId: string, payload: ReserveRowPayload) =>
      onReserve(requestId, rowId, payload, Object.keys(confirmedRows)),
    [onReserve, confirmedRows],
  );

  const soleRow = effectiveRows[0];
  // Nit (fix round 2): every row in a multi-row dialog shares ONE request - the
  // "Request #N - requested by X on <date>" line renders ONCE, here in the header,
  // rather than once per section. No per-row qty in it (each row's own requested qty
  // differs, and stays with that row's own Reserved input) - unlike the single-row
  // (tabs) path's own line, which keeps its qty exactly as before (AC-RS-61).
  const multiRowOpenRequest = !showTabs
    ? (effectiveRows.find((row) => row.openRequest)?.openRequest ?? null)
    : null;
  // F2 (fix round 3 review finding): whether ANY carried row is still open THIS
  // session - `canAct` used to be folded into this check, so a viewer without the
  // reserve permission saw the empty line while rows were genuinely still open
  // (AC-RS-62 says read-only, not emptied). The empty line now renders only once
  // nothing is left open at all; `!canAct` alone renders every section READ-ONLY
  // instead (each `ReserveRowSection` already gates its own inputs/Confirm on its
  // own `canAct` prop).
  const hasOpenSection = effectiveRows.some((row) => confirmedRows[row.rowId] == null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* G6: a multi-row grid needs the wider dialog + horizontal scroll room the
          single-row (tabs) form never did - the single-row path keeps its old
          `sm:max-w-lg`. */}
      <DialogContent className={showTabs ? 'sm:max-w-lg' : 'sm:max-w-4xl'}>
        <DialogHeader className="pe-10">
          <div className="flex flex-row flex-wrap items-center justify-between gap-2">
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
          </div>
          {multiRowOpenRequest ? (
            <p className="text-sm text-muted-foreground">
              Request #{multiRowOpenRequest.ordinal} - requested
              {multiRowOpenRequest.requestedByName ? ` by ${multiRowOpenRequest.requestedByName}` : ''}
              {multiRowOpenRequest.requestedAt
                ? ` on ${formatDateTime(multiRowOpenRequest.requestedAt)}`
                : ''}
            </p>
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
                  // R1 (fix round 3): the read-only echo shows ONLY while props are
                  // still STALE (`soleRow.openRequest` truthy) - the moment the
                  // caller's own props catch up (a refetch lands `openRequest: null`),
                  // this falls through to `ReserveRowSection` itself, which is where
                  // the REAL "Reserved N @ Location" + Unreserve branch lives. The old
                  // gate (`confirmedRows[...] != null` alone) hid that branch for the
                  // WHOLE session, so Unreserve stayed unreachable until the dialog
                  // was closed and reopened.
                  confirmedRows[soleRow.rowId] != null && soleRow.openRequest ? (
                    <div className="flex items-center gap-2 rounded-lg border border-border p-3">
                      <Check className="size-4 text-emerald-600" aria-hidden />
                      <span className="text-sm text-muted-foreground">
                        Reserved {confirmedRows[soleRow.rowId].qty}
                        {confirmedRows[soleRow.rowId].location
                          ? ` @ ${confirmedRows[soleRow.rowId].location}`
                          : ''}
                      </span>
                    </div>
                  ) : (
                    <ReserveRowSection
                      row={soleRow}
                      locationOptions={soleRow.locationOptions ?? locationOptions}
                      defaultLocationId={soleRow.defaultLocationId ?? defaultLocationId}
                      availableQtyByLocation={soleRow.availableQtyByLocation ?? availableQtyByLocation}
                      canAct={canAct}
                      onReserve={handleReserve}
                      onRowConfirmed={handleRowConfirmed}
                      unreserveControl={unreserveControl}
                    />
                  )
                ) : null}
              </TabsContent>

              <TabsContent value="history" className="mt-0 focus-visible:outline-none">
                <HistoryPanel history={soleRow?.history ?? []} />
              </TabsContent>
            </Tabs>
          ) : !hasOpenSection ? (
            // F2 (fix round 3): nothing left OPEN at all - every carried row already
            // confirmed this session (which also closes the dialog, so this is
            // reached mainly by a caller handing the dialog zero rows), never by
            // `canAct` alone (a viewer without the permission still sees every
            // section, read-only, below).
            <p className="text-sm text-muted-foreground">
              Nothing left to reserve on this request.
            </p>
          ) : (
            // G6 (AC-RS-74): no stacked cards - ONE DataGrid, one row per product.
            // `ReserveRowsGrid` owns its own per-row draft state (there is no mounted
            // `ReserveRowSection` instance per row any more to hold it) and calls
            // `handleReserve` (per-row Confirm reserved, O3's wrapping) or the raw
            // `onReserve` prop (Confirm all, which builds its own 4th arg as it walks
            // the still-open rows). `showRequestLine`'s old job - a read-only viewer
            // still sees what was requested - is met unconditionally by the Requested
            // column now, rather than a conditional text line.
            <ReserveRowsGrid
              rows={effectiveRows}
              locationOptions={locationOptions}
              defaultLocationId={defaultLocationId}
              availableQtyByLocation={availableQtyByLocation}
              canAct={canAct}
              onReserve={onReserve}
              handleReserve={handleReserve}
              confirmedRows={confirmedRows}
              onRowConfirmed={handleRowConfirmed}
            />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveRowDialog;
