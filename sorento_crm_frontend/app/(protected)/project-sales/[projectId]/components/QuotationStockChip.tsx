'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { CellStockTable } from '../../fulfilment-planning/components/CellStockTable';
import { useQuotationLineStock } from '../../_shared/hooks/useFulfilmentPlanning';
import type {
  StockDetail,
  StockDetailIncoming,
} from '../../_shared/types/fulfilmentPlanning.types';
import { useStockStatus } from '@/components/stock-status/useStockStatus';
import type {
  StockStatus,
  StockStatusLocation,
} from '@/components/stock-status/stockStatus.types';

type StockTone = 'ok' | 'part' | 'none';

/** Green covers the quoted qty, amber covers some of it, red covers none (AC-QLG15). */
function toneOf(available: number, wanted: number): StockTone {
  if (!(available > 0)) return 'none';
  if (!(wanted > 0) || available >= wanted) return 'ok';
  return 'part';
}

const TONE_VARIANT: Record<StockTone, 'success' | 'warning' | 'destructive'> = {
  ok: 'success',
  part: 'warning',
  none: 'destructive',
};

/** `25.00` reads as 25: stock is a count. Signed, never clamped. */
function trimQty(value: string | null | undefined): string {
  const amount = Number(value ?? '');
  if (value == null || Number.isNaN(amount)) return value ?? '';
  return String(amount);
}

/**
 * Available stock for the line's product over the locations the user's contact may see, toned
 * against the quoted qty, opening the same stock table Order Inquiry shows (AC-QLG15, AC-QLG16).
 * Read-only, and only on a line with a product. A read that answers null draws nothing.
 */
export function QuotationStockChip({
  productId,
  quantity,
  uom,
  label,
}: {
  productId: string;
  quantity: string;
  uom: string;
  label: string;
}) {
  const detail = useQuotationLineStock(productId);

  if (detail.data === null) return null;
  if (detail.isLoading || (!detail.data && !detail.isError)) {
    return <Skeleton className="h-5 w-16 rounded-full" />;
  }
  if (detail.isError || !detail.data) {
    return (
      <span
        className="text-2xs text-muted-foreground"
        title="Stock could not be loaded"
      >
        Stock -
      </span>
    );
  }

  const available = detail.data.available_qty;
  const tone = toneOf(Number(available), Number(quantity));

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Badge
          asChild
          variant={TONE_VARIANT[tone]}
          appearance="light"
          size="sm"
        >
          <button
            type="button"
            aria-label={`Stock on ${label}`}
            data-tone={tone}
            className="cursor-pointer whitespace-nowrap tabular-nums"
          >
            {`${trimQty(available)} avail`}
          </button>
        </Badge>
      </PopoverTrigger>
      {/* Portalled: a row being a drag target is its own stacking context, so a popover left
          inside it paints under the next row and a click lands on that row instead. */}
      <PopoverPortal>
        <PopoverContent
          align="end"
          // Radix keeps it on screen (avoidCollisions is on by default); the padding keeps it off
          // the very edge, and the cap lets a long table scroll inside the room it has.
          collisionPadding={8}
          className="max-h-[var(--radix-popover-content-available-height)] w-[min(36rem,calc(100vw-2rem))] space-y-2 overflow-y-auto p-3"
        >
          <StockPopoverBody
            productId={productId}
            label={label}
            quantity={quantity}
            uom={uom}
            locations={detail.data.locations ?? []}
            incoming={detail.data.incoming ?? []}
          />
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

type StockLocations = NonNullable<StockDetail['locations']>;

/** A location with no stock, no sales order and no SPO is noise in the popover. */
function hasFigures(row: StockLocations[number]): boolean {
  return (
    Number(row.qty_on_hand) !== 0 ||
    Number(row.so_qty) !== 0 ||
    Number(row.spo_qty) !== 0
  );
}

/**
 * AutoCount's read narrowed to the locations the quotation read listed: its other locations, and
 * the documents and totals that belong to them, never reach the table (any Group by draws them).
 */
function onlyLocations(status: StockStatus, codes: Set<string>): StockStatus {
  const locations = status.locations.filter((loc) => codes.has(loc.warehouse_code));
  const ids = new Set(locations.map((loc) => loc.warehouse_id));
  const sum = (pick: (loc: StockStatusLocation) => number) =>
    locations.reduce((total, loc) => total + pick(loc), 0);
  return {
    ...status,
    locations,
    totals: {
      on_hand: sum((loc) => loc.on_hand),
      so_qty: sum((loc) => loc.so_qty),
      po_qty: sum((loc) => loc.po_qty),
      spo_qty: sum((loc) => loc.spo_qty),
      forecast: sum((loc) => loc.forecast),
      incoming_pl: 0,
      forecast_incl_pl: sum((loc) => loc.forecast),
    },
    incoming_pl: [],
    sales_orders: (status.sales_orders ?? []).filter((row) => ids.has(row.warehouse_id)),
    purchase_orders: (status.purchase_orders ?? []).filter((row) => ids.has(row.warehouse_id)),
    spos: (status.spos ?? []).filter((row) => ids.has(row.warehouse_id)),
  };
}

function StockPopoverBody({
  productId,
  label,
  quantity,
  uom,
  locations,
  incoming,
}: {
  productId: string;
  label: string;
  quantity: string;
  uom: string;
  locations: StockLocations;
  incoming: StockDetailIncoming[];
}) {
  // STOCK-STATUS round 6 (owner 06:00 and the v6 OK, UAC AC-35): the table is read against
  // AutoCount, so its figures and PO qty show. It restates the read's rows only; a location the
  // user may not see never joins from AutoCount. A failed read leaves today's figures.
  const autoCount = useStockStatus(productId);
  const allowedStatus = React.useMemo(
    () =>
      autoCount.data
        ? onlyLocations(autoCount.data, new Set(locations.map((row) => row.location ?? '')))
        : null,
    [autoCount.data, locations],
  );

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">{`${label} stock`}</p>
        <p className="text-xs text-muted-foreground">
          {`Quoted ${trimQty(quantity)}${uom ? ` ${uom}` : ''}`}
        </p>
      </div>
      {autoCount.isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <CellStockTable
          locations={locations.filter(hasFigures)}
          showGroupSubtotal
          stockOnly
          autoCount={allowedStatus}
        />
      )}
      <div className="text-xs text-muted-foreground">
        {incoming.length === 0 ? (
          'No incoming SPO'
        ) : (
          <ul className="space-y-0.5">
            {incoming.map((row, index) => (
              <li key={`${row.spo_number}-${index}`}>
                {'Incoming: '}
                <span className="font-medium text-foreground">
                  {row.spo_number}
                </span>
                {`, ${trimQty(row.spo_qty)}`}
                {row.expected_date
                  ? `, expected ${formatDateInMalaysia(row.expected_date)}`
                  : ''}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

export interface SetStockPart {
  product_id: string;
  product_code: string;
  quantity: string | number;
}

/** Reads one part's stock and reports it up; draws nothing. */
function PartProbe({
  part,
  onRead,
}: {
  part: SetStockPart;
  onRead: (productId: string, available: number | null, failed: boolean, blank: boolean) => void;
}) {
  const detail = useQuotationLineStock(part.product_id);
  const data = detail.data;
  const failed = detail.isError;
  React.useEffect(() => {
    // A null answer (the user may see no stock for the part) blanks the whole set chip.
    onRead(part.product_id, data ? Number(data.available_qty) : null, failed, data === null);
  }, [part.product_id, data, failed, onRead]);
  return null;
}

function PartStockSection({ part }: { part: SetStockPart }) {
  const detail = useQuotationLineStock(part.product_id);
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold">
        {`${part.product_code}${Number(part.quantity) !== 1 ? ` x ${trimQty(String(part.quantity))}` : ''}`}
      </p>
      {detail.isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : detail.data ? (
        <CellStockTable
          locations={(detail.data.locations ?? []).filter(hasFigures)}
          showGroupSubtotal
          stockOnly
        />
      ) : detail.data === null ? null : (
        <p className="text-xs text-muted-foreground">Stock could not be loaded</p>
      )}
    </div>
  );
}

/**
 * The stock pill of a SET line: how many complete sets the user's allowed locations can make, that
 * is the smallest of floor(part available / part quantity). Every part is read through
 * `useQuotationLineStock`, one
 * child per part (never a hook in a loop), and the popover lists each part with its stock table.
 */
export function SetStockChip({
  parts,
  quantity,
  label,
}: {
  parts: SetStockPart[];
  quantity: string;
  label: string;
}) {
  const [reads, setReads] = React.useState<
    Record<string, { available: number | null; failed: boolean; blank: boolean }>
  >({});
  const onRead = React.useCallback(
    (productId: string, available: number | null, failed: boolean, blank: boolean) =>
      setReads((previous) =>
        previous[productId]?.available === available &&
        previous[productId]?.failed === failed &&
        previous[productId]?.blank === blank
          ? previous
          : { ...previous, [productId]: { available, failed, blank } },
      ),
    [],
  );

  if (parts.length === 0) return null;
  const probes = parts.map((part) => (
    <PartProbe key={part.product_id} part={part} onRead={onRead} />
  ));
  const read = parts.map((part) => reads[part.product_id]);
  if (read.some((entry) => entry?.blank)) return <>{probes}</>;
  if (read.some((entry) => entry?.failed)) {
    return (
      <>
        {probes}
        <span className="text-2xs text-muted-foreground" title="Stock could not be loaded">
          Stock -
        </span>
      </>
    );
  }
  if (read.some((entry) => !entry || entry.available === null)) {
    return (
      <>
        {probes}
        <Skeleton className="h-5 w-16 rounded-full" />
      </>
    );
  }
  const sets = Math.min(
    ...parts.map((part, index) => {
      const per = Number(part.quantity) > 0 ? Number(part.quantity) : 1;
      return Math.floor((read[index]?.available ?? 0) / per);
    }),
  );
  const available = Math.max(sets, 0);
  const tone = toneOf(available, Number(quantity));
  return (
    <>
      {probes}
      <Popover>
        <PopoverTrigger asChild>
          <Badge asChild variant={TONE_VARIANT[tone]} appearance="light" size="sm">
            <button
              type="button"
              aria-label={`Stock on ${label}`}
              data-tone={tone}
              className="cursor-pointer whitespace-nowrap tabular-nums"
            >
              {`${available} avail`}
            </button>
          </Badge>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent
            align="end"
            collisionPadding={8}
            className="max-h-[var(--radix-popover-content-available-height)] w-[min(36rem,calc(100vw-2rem))] space-y-3 overflow-y-auto p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold">{`${label} stock`}</p>
              <p className="text-xs text-muted-foreground">{`Quoted ${trimQty(quantity)} sets`}</p>
            </div>
            {parts.map((part) => (
              <PartStockSection key={part.product_id} part={part} />
            ))}
          </PopoverContent>
        </PopoverPortal>
      </Popover>
    </>
  );
}
