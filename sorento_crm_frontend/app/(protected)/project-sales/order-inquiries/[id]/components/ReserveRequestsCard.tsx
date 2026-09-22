'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { reserveOrderInquiryRequest } from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` 3.7/3.8, `oi-request-cs-reserve-acceptance-criteria.md`
 * AC-RS-24 (request mode, the requester's own card) and AC-RS-26/AC-RS-27 (act mode,
 * Eling's own Confirm).
 *
 * `mode="request"` shows the ask as read history (requested qty + location, who / when);
 * `mode="act"` (only when `canAct`) turns each row into Location + Reserved inputs with a
 * Reason box the moment Reserved drops below Requested. A viewer without the permission
 * always sees the read-only rendering, whichever `mode` is asked for.
 */
export interface ReserveRequestsCardRow {
  id: string;
  item_code: string | null;
  qty_requested: string;
  /** Server-computed default (plan 3.8): `min(requested, available at the location)`,
   * floored at 0 - this card is handed the number already resolved. */
  default_reserved: string;
  location_options: SearchableSelectOption[];
  default_location: string;
  qty_reserved?: string | null;
  reason?: string | null;
  /** AC-RS-28: `available_qty` per warehouse id this row's own stock grid carries, so
   * Reserved can recompute when Location changes - only while the reader has not
   * touched Reserved yet on this row. */
  available_qty_by_location?: Record<string, number>;
}

export interface ReserveRequestsCardRequest {
  id: string;
  ordinal: number;
  state: 'requested' | 'reserved' | 'cancelled';
  requested_by_name: string | null;
  requested_at: string | null;
  rows: ReserveRequestsCardRow[];
}

/**
 * The Cancel button's own countdown, built by the CALLER (`useDeferredAction` needs a
 * `QueryClientProvider` this card is deliberately kept free of, so its own vitest suite
 * can render it with no providers at all) - AC-RS-24's "Cancel request" becomes the
 * standard reversible countdown once `start()` is pressed.
 */
export interface ReserveRequestsCardCancelControl {
  isPending: boolean;
  isBlocked: boolean;
  countdown: React.ReactNode;
  start: () => void;
}

const STATE_LABEL: Record<string, string> = {
  requested: 'Request to reserve',
  reserved: 'Reserved',
  cancelled: 'Cancelled',
};

export function ReserveRequestsCard({
  request,
  mode,
  canAct,
  onConfirmed,
  cancelControl,
}: {
  request: ReserveRequestsCardRequest;
  mode: 'request' | 'act';
  canAct: boolean;
  onConfirmed?: () => void;
  /** AC-RS-24: present only for the requester (or a reserve-permission holder), and
   * only while the request is still open - the caller decides both, this card only
   * renders what it is handed. */
  cancelControl?: ReserveRequestsCardCancelControl | null;
}) {
  const [reserved, setReserved] = React.useState<Record<string, number>>({});
  const [location, setLocation] = React.useState<Record<string, string>>({});
  const [reason, setReason] = React.useState<Record<string, string>>({});
  const [editedReserved, setEditedReserved] = React.useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = React.useState(false);

  React.useEffect(() => {
    setReserved(
      Object.fromEntries(
        request.rows.map((row) => [row.id, Number(row.default_reserved || '0')]),
      ),
    );
    setLocation(Object.fromEntries(request.rows.map((row) => [row.id, row.default_location])));
    setReason({});
    setEditedReserved({});
  }, [request.id, request.rows]);

  const isActMode = mode === 'act' && canAct;

  const rowsWithComputed = request.rows.map((row) => {
    const requestedQty = Number(row.qty_requested || '0');
    const reservedQty = reserved[row.id] ?? Number(row.default_reserved || '0');
    return { row, requestedQty, reservedQty, short: reservedQty < requestedQty };
  });
  const canConfirm = rowsWithComputed
    .filter((entry) => entry.short)
    .every((entry) => (reason[entry.row.id] || '').trim().length > 0);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await reserveOrderInquiryRequest(request.id, {
        rows: request.rows.map((row) => {
          const reservedQty = reserved[row.id] ?? Number(row.default_reserved || '0');
          const reasonText = (reason[row.id] || '').trim();
          return {
            request_row_id: row.id,
            warehouse_id: location[row.id] ?? row.default_location,
            qty_reserved: reservedQty,
            reason: reasonText ? reasonText : null,
          };
        }),
      });
      toast.success(`Reserved, ${request.requested_by_name ?? 'the requester'} notified`);
      onConfirmed?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to confirm the reserve');
    } finally {
      setConfirming(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 py-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <span>Request #{request.ordinal}</span>
          <Badge variant="secondary" appearance="light" size="sm">
            {STATE_LABEL[request.state] ?? request.state}
          </Badge>
        </CardTitle>
        <div className="flex items-center gap-3">
          {request.requested_by_name ? (
            <span className="text-xs text-muted-foreground">
              Requested by {request.requested_by_name}
              {request.requested_at ? ` on ${request.requested_at}` : ''}
            </span>
          ) : null}
          {mode === 'request' && cancelControl && request.state === 'requested' ? (
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
      </CardHeader>
      <CardContent className="space-y-3">
        {rowsWithComputed.map(({ row, requestedQty, reservedQty, short }) => (
          <div key={row.id} className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{row.item_code}</span>
              <span className="text-xs text-muted-foreground">Requested {row.qty_requested}</span>
            </div>
            {isActMode ? (
              <>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor={`reserve-act-location-${row.id}`}>Location</Label>
                    <SearchableSelect
                      id={`reserve-act-location-${row.id}`}
                      value={location[row.id] ?? row.default_location}
                      onChange={(value) => {
                        setLocation((prev) => ({ ...prev, [row.id]: value }));
                        // AC-RS-28: Reserved recomputes from the NEW location's own
                        // availability, but only while the reader has not touched
                        // Reserved on this row yet - an edit they made stands.
                        if (!editedReserved[row.id]) {
                          const available = row.available_qty_by_location?.[value];
                          const next =
                            available == null
                              ? requestedQty
                              : Math.max(0, Math.min(requestedQty, available));
                          setReserved((prev) => ({ ...prev, [row.id]: next }));
                        }
                      }}
                      options={row.location_options}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`reserve-act-qty-${row.id}`}>Reserved</Label>
                    <Input
                      id={`reserve-act-qty-${row.id}`}
                      type="number"
                      min={0}
                      max={requestedQty}
                      value={reservedQty}
                      onChange={(event) => {
                        const raw = Number(event.target.value);
                        const capped = Math.min(Math.max(raw || 0, 0), requestedQty);
                        setEditedReserved((prev) => ({ ...prev, [row.id]: true }));
                        setReserved((prev) => ({ ...prev, [row.id]: capped }));
                      }}
                    />
                  </div>
                </div>
                {short ? (
                  <div className="space-y-1">
                    <Label htmlFor={`reserve-act-reason-${row.id}`}>Reason</Label>
                    <Input
                      id={`reserve-act-reason-${row.id}`}
                      value={reason[row.id] ?? ''}
                      onChange={(event) =>
                        setReason((prev) => ({ ...prev, [row.id]: event.target.value }))
                      }
                    />
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-xs text-muted-foreground">
                Location{' '}
                {row.location_options.find((option) => option.value === row.default_location)
                  ?.label ?? row.default_location}
                {row.qty_reserved != null ? ` - reserved ${row.qty_reserved}` : null}
                {row.reason ? ` (${row.reason})` : null}
              </div>
            )}
          </div>
        ))}
      </CardContent>
      {isActMode ? (
        <div className="flex justify-end gap-2 border-t border-border p-3">
          <Button onClick={handleConfirm} disabled={!canConfirm || confirming}>
            Confirm reserved
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

export default ReserveRequestsCard;
