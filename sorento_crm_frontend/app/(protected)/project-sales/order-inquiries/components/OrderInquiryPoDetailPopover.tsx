'use client';

import * as React from 'react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { statusPillClass } from '@/lib/status-pill';
import { useOrderInquiryPoDetail } from '../../_shared/hooks/useOrderInquiry';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';

/**
 * The "PO no" cell's popup (the captain, 20 Aug): clicking a placed row's purchase order
 * number opens that PO's own header and every one of its lines, not only the one this
 * row happened to be tagged to.
 *
 * Same primitives as `BoardTrailPopover` / `ClassificationProofPopover` - a real
 * `<table>` inside a `Popover`, fetched only while it is open, `stopPropagation` on the
 * trigger so a click here never reaches the row's own actions.
 */
export function OrderInquiryPoDetailPopover({
  poId,
  poNumber,
}: {
  poId: string;
  poNumber: string;
}) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading, isError } = useOrderInquiryPoDetail(poId, { enabled: open });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid={`po-detail-trigger-${poId}`}
          className="block max-w-full truncate rounded-sm tabular-nums font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          title={poNumber}
          onClick={(event) => event.stopPropagation()}
        >
          {poNumber}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="start"
          className="w-[520px] max-w-[92vw] p-0"
          // Read-only content - it does not need focus, and taking it can read to a
          // surrounding dialog as focus leaving and close it (the `BoardTrailPopover`
          // lesson).
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          <div data-testid={`po-detail-${poId}`} className="max-h-[60vh] overflow-y-auto">
            {isLoading && (
              <div className="space-y-2 p-3">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-16 w-full" />
              </div>
            )}
            {isError && !isLoading && (
              <p className="p-3 text-xs text-destructive">
                Could not load this purchase order.
              </p>
            )}
            {data && !isLoading && !isError && <PoDetailBody detail={data} />}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function PoDetailBody({
  detail,
}: {
  detail: NonNullable<ReturnType<typeof useOrderInquiryPoDetail>['data']>;
}) {
  const supplier =
    [detail.supplier_code, detail.supplier_name].filter(Boolean).join(' - ') || null;

  return (
    <div>
      <div className="space-y-1 border-b px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold tabular-nums">{detail.po_number}</span>
          <span
            className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium capitalize ${statusPillClass(detail.status)}`}
          >
            {detail.status}
          </span>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-2xs">
          <div className="min-w-0">
            <dt className="text-muted-foreground">Supplier</dt>
            <dd className="truncate font-medium" title={supplier ?? undefined}>
              {supplier ?? <span className="text-muted-foreground">Not stated</span>}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground">Expected</dt>
            <dd className="font-medium">
              {detail.expected_date ? (
                formatDateInMalaysia(detail.expected_date)
              ) : (
                <span className="text-muted-foreground">No date</span>
              )}
            </dd>
          </div>
        </dl>
      </div>

      {detail.lines.length === 0 ? (
        <p className="px-3 py-3 text-xs text-muted-foreground">
          This purchase order carries no lines.
        </p>
      ) : (
        <div className="overflow-x-auto overscroll-x-contain">
          <table className="w-full min-w-[480px] text-2xs tabular-nums">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="px-3 py-1.5 text-start font-medium uppercase tracking-wide">
                  SKU
                </th>
                <th className="px-2 py-1.5 text-end font-medium uppercase tracking-wide">
                  Ordered
                </th>
                <th className="px-2 py-1.5 text-end font-medium uppercase tracking-wide">
                  Received
                </th>
                <th className="px-2 py-1.5 text-end font-medium uppercase tracking-wide">
                  Remaining
                </th>
                <th className="px-3 py-1.5 text-start font-medium uppercase tracking-wide">
                  Location
                </th>
              </tr>
            </thead>
            <tbody>
              {detail.lines.map((line, index) => (
                <tr key={`${line.sku ?? 'line'}-${index}`} className="border-b last:border-b-0">
                  <td className="px-3 py-1.5">
                    <div className="min-w-0">
                      <span className="block truncate font-medium" title={line.sku ?? ''}>
                        {line.sku || <span className="text-muted-foreground">Unresolved</span>}
                      </span>
                      {line.product_name && line.product_name !== line.sku && (
                        <span
                          className="block truncate text-muted-foreground"
                          title={line.product_name}
                        >
                          {line.product_name}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-1.5 text-end">{formatInquiryQty(line.qty_ordered)}</td>
                  <td className="px-2 py-1.5 text-end">{formatInquiryQty(line.qty_received)}</td>
                  <td className="px-2 py-1.5 text-end font-medium">
                    {formatInquiryQty(line.remaining)}
                  </td>
                  <td className="px-3 py-1.5">
                    {line.location || <span className="text-muted-foreground">-</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default OrderInquiryPoDetailPopover;
