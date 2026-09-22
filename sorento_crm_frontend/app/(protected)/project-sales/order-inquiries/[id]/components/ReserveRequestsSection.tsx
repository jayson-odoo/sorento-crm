'use client';

import * as React from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  ORDER_INQUIRY_HEADER_LINES_KEY,
  ORDER_INQUIRY_RESERVE_REQUESTS_KEY,
  useOrderInquiryReserveRequests,
} from '../../../_shared/hooks/useOrderInquiry';
import { useReserveRowOptions } from '../../../_shared/hooks/useReserveRowOptions';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import { ReserveRequestsCard, type ReserveRequestsCardRow } from './ReserveRequestsCard';

/**
 * `PLAN-oi-request-cs-reserve.md` 3.7/3.8, AC-RS-24/AC-RS-25/AC-RS-26/AC-RS-33: the Lines
 * tab's own card above the grid - the open request (in act mode for `?reserve=<id>` or a
 * reserve-permission holder, request mode otherwise), collapsed history below it. Hidden
 * entirely when this header has never raised one.
 *
 * `useReserveRowOptions` resolves each open row's own pool default + stock-grid options
 * the SAME way the "Request CS to reserve" dialog does (one shared hook, `useOrderInquiry
 * .ts`'s own doc comment on why the two writers never duplicate this).
 */
export function ReserveRequestsSection({
  inquiryId,
  lines,
  canRequest,
  canReserve,
}: {
  inquiryId: string;
  lines: OrderInquiryWorklistRow[];
  /** Whoever may raise a request also may cancel their own (AC-RS-24's "the requester or
   * a reserve-permission holder"). */
  canRequest: boolean;
  canReserve: boolean;
}) {
  const searchParams = useSearchParams();
  const activeReserveId = searchParams.get('reserve');
  const queryClient = useQueryClient();
  const sectionRef = React.useRef<HTMLDivElement | null>(null);
  const scrolledRef = React.useRef<string | null>(null);

  const { data: requests } = useOrderInquiryReserveRequests(inquiryId);
  const openRequest = React.useMemo(
    () => (requests ?? []).find((request) => request.state === 'requested') ?? null,
    [requests],
  );
  const history = React.useMemo(
    () => (requests ?? []).filter((request) => request.state !== 'requested'),
    [requests],
  );

  const lineById = React.useMemo(
    () => new Map(lines.map((line) => [line.id, line])),
    [lines],
  );

  const entries = React.useMemo(
    () =>
      (openRequest?.rows ?? []).map((row) => ({
        key: row.id,
        productId: lineById.get(row.row_id)?.product_id ?? null,
        location: row.location,
      })),
    [openRequest, lineById],
  );
  const resolved = useReserveRowOptions(entries);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_HEADER_LINES_KEY, inquiryId] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, inquiryId] });
  }

  const cancelAction = useDeferredAction({
    actionKey: 'order_inquiry_reserve_request.cancel',
    entityType: 'order_inquiry_reserve_request',
    entityId: openRequest?.id ?? null,
    verb: 'Cancelling',
    subject: openRequest ? `Request #${openRequest.ordinal}` : '',
    surface: 'inline',
    watchFromMount: Boolean(openRequest),
    successMessage: 'Reserve request cancelled',
    invalidateKeys: [
      [ORDER_INQUIRY_HEADER_LINES_KEY, inquiryId],
      [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, inquiryId],
    ],
  });

  React.useEffect(() => {
    if (
      activeReserveId &&
      openRequest?.id === activeReserveId &&
      scrolledRef.current !== activeReserveId
    ) {
      scrolledRef.current = activeReserveId;
      sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [activeReserveId, openRequest?.id]);

  if (!openRequest && history.length === 0) return null;

  const actMode = Boolean(activeReserveId && activeReserveId === openRequest?.id) || canReserve;

  const cardRows: ReserveRequestsCardRow[] = (openRequest?.rows ?? []).map((row) => {
    const own = resolved[row.id];
    const requestedQty = Number(row.qty_requested || '0');
    const availableAtDefault =
      own?.defaultWarehouseId != null
        ? (own.availableQtyByWarehouseId[own.defaultWarehouseId] ?? 0)
        : 0;
    const defaultReserved = Math.max(0, Math.min(requestedQty, availableAtDefault));
    return {
      id: row.id,
      item_code: row.item_code,
      qty_requested: row.qty_requested,
      default_reserved: String(defaultReserved),
      location_options:
        own?.options ??
        (row.warehouse_id && row.location
          ? [{ value: row.warehouse_id, label: row.location }]
          : []),
      default_location: own?.defaultWarehouseId ?? row.warehouse_id ?? '',
      qty_reserved: row.qty_reserved,
      reason: row.reason,
      available_qty_by_location: own?.availableQtyByWarehouseId,
    };
  });

  return (
    <div ref={sectionRef} className="space-y-3">
      {openRequest ? (
        <ReserveRequestsCard
          request={{
            id: openRequest.id,
            ordinal: openRequest.ordinal,
            state: openRequest.state,
            requested_by_name: openRequest.requested_by_name,
            requested_at: openRequest.requested_at,
            rows: cardRows,
          }}
          mode={actMode ? 'act' : 'request'}
          canAct={canReserve}
          onConfirmed={invalidate}
          cancelControl={
            canRequest || canReserve
              ? {
                  isPending: cancelAction.isPending,
                  isBlocked: cancelAction.isBlocked,
                  countdown: cancelAction.countdown,
                  start: () => cancelAction.start(),
                }
              : null
          }
        />
      ) : null}
      {history.length > 0 ? (
        <details className="rounded-lg border border-border p-3 text-sm">
          <summary className="cursor-pointer select-none text-muted-foreground">
            Earlier reserve requests ({history.length})
          </summary>
          <div className="mt-2 space-y-2">
            {history.map((request) => (
              <div key={request.id} className="rounded-md border border-border p-2 text-xs">
                <div className="font-medium">
                  Request #{request.ordinal}
                  {' - '}
                  {request.state === 'reserved' ? 'Reserved' : 'Cancelled'}
                </div>
                {request.rows.map((row) => (
                  <div key={row.id} className="text-muted-foreground">
                    {row.item_code}
                    {request.state === 'reserved'
                      ? `: reserved ${row.qty_reserved ?? '0'}`
                      : ''}
                    {row.reason ? ` (${row.reason})` : ''}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

export default ReserveRequestsSection;
