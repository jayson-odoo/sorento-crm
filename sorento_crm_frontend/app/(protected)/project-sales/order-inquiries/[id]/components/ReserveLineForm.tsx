'use client';

import * as React from 'react';
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
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { bareLocationCode } from '../../../_shared/lib/orderInquiryReserve';

/**
 * `PLAN-oi-request-cs-reserve.md` section 6e.2 (round 4, 24 Sep), AC-RS-85 (reserve
 * mode) / AC-RS-86 (amend mode). A small dialog whose ONLY job is to hand back a
 * STAGED decision through `onStage` - it never posts anything itself (the Lines grid's
 * own header `Reserve (N)` CTA does the one batched commit, `OrderInquiryDetail.tsx`
 * owns the staged map). Replaces `ReserveRowDialog`'s per-row `ReserveRowSection`.
 *
 * Reserve mode: Location is a `SearchableSelect` (options = the row's own pools with
 * availability), Reserved defaults to `min(requested, available at the chosen pool)`
 * and recomputes to that ceiling every time Location changes. Amend mode: Location is
 * locked read-only text (the row's own answered location never changes on an amend),
 * Reserved starts at the row's own net reserved.
 *
 * A reason is required whenever the staged qty reads short of the CEILING it could
 * reach right now (reserve mode: `min(requested, available at the CHOSEN location)`;
 * amend mode: `requested`, there being no availability axis once the location is
 * locked) - not merely short of the original ask, so switching to a smaller pool and
 * leaving Reserved at that pool's own full availability needs no explaining, only a
 * reader-typed reduction below what is actually on offer does.
 */
export interface ReserveLineFormStagePayload {
  warehouse_id: string;
  qty_reserved: number;
  reason: string | null;
}

export interface ReserveLineFormAmendPayload {
  qty_reserved: number;
  reason: string | null;
}

export interface ReserveLineFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  itemCode: string | null;
  mode: 'reserve' | 'amend';
  /** The request row's own `qty_requested` - the input's own ceiling either way. */
  requestedQty: string;
  /** Reserve mode only: the row's own pools, `available_qty` per warehouse id, and
   * which one Reserved defaults to. */
  locationOptions?: SearchableSelectOption[];
  availableQtyByLocation?: Record<string, number>;
  defaultLocationId?: string | null;
  /** Amend mode only: the answered location's own code (read-only text, never a
   * `SearchableSelect` - the location itself is locked on an amend), and the row's
   * own net reserved qty to prefill Reserved with. */
  lockedLocationLabel?: string;
  initialQty?: string;
  onStage: (payload: ReserveLineFormStagePayload | ReserveLineFormAmendPayload) => void;
}

export function ReserveLineForm({
  open,
  onOpenChange,
  itemCode,
  mode,
  requestedQty,
  locationOptions = [],
  availableQtyByLocation = {},
  defaultLocationId = null,
  lockedLocationLabel,
  initialQty,
  onStage,
}: ReserveLineFormProps) {
  const requested = Number(requestedQty || '0');

  // The PREFILL ceiling (what Reserved auto-sets to, on mount and on every Location
  // switch) reads PESSIMISTIC while availability at that location is not yet known
  // (0 - never overstate what CS could actually reserve); the REQUIREMENT ceiling
  // (whether a filled Reason is what unblocks Stage) reads OPTIMISTIC in that same
  // gap (the full requested amount - do not demand an explanation for a qty that is
  // only "short" because the availability read has not landed yet, never a real CS
  // decision). The two converge the moment availability is actually known.
  const ceilingFor = React.useCallback(
    (locationId: string): number => {
      if (mode === 'amend') return requested;
      const available = availableQtyByLocation[locationId];
      return available != null ? Math.min(requested, available) : 0;
    },
    [mode, requested, availableQtyByLocation],
  );
  const gateCeilingFor = React.useCallback(
    (locationId: string): number => {
      if (mode === 'amend') return requested;
      const available = availableQtyByLocation[locationId];
      return available != null ? Math.min(requested, available) : requested;
    },
    [mode, requested, availableQtyByLocation],
  );

  const [location, setLocation] = React.useState(() => defaultLocationId ?? '');
  const [qty, setQty] = React.useState(() =>
    mode === 'amend'
      ? Math.max(0, Number(initialQty || '0'))
      : Math.max(0, ceilingFor(defaultLocationId ?? '')),
  );
  const [reason, setReason] = React.useState('');

  function handleLocationChange(value: string) {
    setLocation(value);
    setQty(Math.max(0, ceilingFor(value)));
  }

  function handleQtyChange(event: React.ChangeEvent<HTMLInputElement>) {
    const raw = Number(event.target.value);
    setQty(Math.min(Math.max(Number.isFinite(raw) ? raw : 0, 0), requested));
  }

  // AC-RS-85's own words: "Reason appears when Reserved < Requested" - the FIELD's
  // own visibility, literal and simple. Whether Stage actually DEMANDS it filled is a
  // narrower question (`reasonRequired`, ceiling-based): a Location switch that lands
  // Reserved exactly on that pool's own full availability is the system's own answer,
  // self-explanatory even though it reads short of the original ask - only a qty that
  // is short of what is actually AVAILABLE needs a reader-typed explanation.
  //
  // AMEND mode never demands one client-side: the true `qty_requested` ceiling AC-RS-78
  // gates the server's own reason requirement on belongs to whichever request originally
  // answered this row, which may already be `reserved` (closed) and is not always still
  // resolvable from the caller's own already-loaded reserve-requests read - `requested`
  // here is `OrderInquiryDetail`'s own best-effort estimate for the INPUT's ceiling, not
  // a value trustworthy enough to BLOCK staging on. The server remains the real gate
  // (AC-RS-78); a rejected commit leaves the staged chip in place and toasts the error
  // (AC-RS-87), so nothing is lost by staging optimistically here.
  const showReason = qty < requested;
  const reasonRequired = mode === 'reserve' && qty < gateCeilingFor(location);
  const canStage = !reasonRequired || reason.trim().length > 0;

  // AC-RS-85: "options = the row's pools with availability" - the availability reads
  // as its own DESCRIPTION line (the shared `SearchableSelect` primitive's own second
  // row), never baked into the primary label - `useReserveRowOptions`' own combined
  // string ("BRW  available 107") would otherwise print in full as the SELECTED
  // value's own trigger text (no UUID in the UI is the letter of the rule; a
  // duplicated "available N" clause on the CLOSED control is the same spirit of it).
  const displayLocationOptions = React.useMemo(
    () =>
      locationOptions.map((option) => {
        const available = availableQtyByLocation[option.value];
        return {
          ...option,
          label: bareLocationCode(option.label),
          description: available != null ? `available ${available}` : option.description,
        };
      }),
    [locationOptions, availableQtyByLocation],
  );

  function handleStage() {
    const cleanReason = showReason ? reason.trim() || null : null;
    if (mode === 'reserve') {
      onStage({ warehouse_id: location, qty_reserved: qty, reason: cleanReason });
    } else {
      onStage({ qty_reserved: qty, reason: cleanReason });
    }
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{itemCode}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {mode === 'reserve' ? (
            <div className="space-y-1">
              <Label htmlFor="reserve-line-location">Location</Label>
              <SearchableSelect
                id="reserve-line-location"
                value={location}
                onChange={handleLocationChange}
                options={displayLocationOptions}
              />
            </div>
          ) : (
            <div className="space-y-1">
              <Label>Location</Label>
              <div className="text-sm">{lockedLocationLabel || '-'}</div>
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="reserve-line-qty">Reserved</Label>
            <Input
              id="reserve-line-qty"
              type="number"
              min={0}
              max={requested}
              step="any"
              value={qty}
              onChange={handleQtyChange}
            />
          </div>
          {showReason ? (
            <div className="space-y-1">
              <Label htmlFor="reserve-line-reason">Reason</Label>
              <Input
                id="reserve-line-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleStage} disabled={!canStage}>
            Stage
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveLineForm;
