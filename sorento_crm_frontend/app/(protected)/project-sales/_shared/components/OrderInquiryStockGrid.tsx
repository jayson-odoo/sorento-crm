'use client';

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import { CellStockTable } from '../../fulfilment-planning/components/CellStockTable';
import { useStockDetail } from '../hooks/useFulfilmentPlanning';
import { useStockStatus } from '@/components/stock-status/useStockStatus';
import { groupOfWarehouseCode } from '../lib/supplyVocabulary';
import type { Warehouse } from '@/app/(protected)/inventory-management/warehouses/types/warehouse.types';

/**
 * The board's own stock position, on the OI Lines tab and the reserve dialog/card
 * (`PLAN-oi-request-cs-reserve.md` 3.9, AC-RS-40/41).
 *
 * A thin wrapper, deliberately: `CellStockTable` already draws the matrix, the group
 * subtotal and the expandable documents panel (each row's own chevron opens
 * `StockDocumentsPanel` internally) - what this component adds is turning a ROW's
 * location CODE into the `group` or `warehouse_id` `stock-detail` wants.
 *
 * The location is resolved to its own warehouse row first, via `getWarehouses` (the only
 * warehouse-list fetcher that carries `id`; `warehouseSelectService` keys by CODE, which
 * `stock-detail` cannot take). Then (MOCHA-STOCK-GRID, crew ruling on #2381):
 *
 * - `BRW-BB`, a bin IN fulfilment planning, is read as its ownership group `BB`
 *   (`groupOfWarehouseCode`). That is the backend's own membership rule: `group_netting`
 *   (planning_only, which `stock-detail` uses) puts a bin in its suffix group only when the
 *   bin is in fulfilment planning.
 * - Any other location - a bare pool code (`BRW`), or a hyphenated bin that belongs to no
 *   ownership group (`MOCHA-WH`, whose suffix is not a group) - is read as the LOCATION
 *   itself, by its own `warehouse_id`. Asking for group `WH` there answered "no stock".
 * - A code the warehouse list does not hold falls back to the suffix group, as before.
 *
 * `useStockDetail`'s own `enabled` gate stays off until that resolution lands, so no request
 * goes out asking for neither a group nor a warehouse (the route 422s on that).
 *
 * Product is always the row's own id, never the item code string - two products share one
 * code on the live book (AC-RS-41).
 */
export function OrderInquiryStockGrid({
  productId,
  /** The row's own `stock_location` / effective location, or null when the row states none. */
  location,
  /** The asking row's own core line, so its documents mark themselves (`StockDocumentsPanel`). */
  lineIds = [],
}: {
  productId: string;
  location: string | null;
  lineIds?: string[];
}) {
  const [resolved, setResolved] = React.useState<{
    location: string;
    warehouse: Warehouse | null;
  } | null>(null);

  React.useEffect(() => {
    if (!location) {
      setResolved(null);
      return;
    }
    let cancelled = false;
    getWarehouses({
      pageIndex: 0,
      // Nit (review round): `getWarehouses` has no exact-code param, and a text
      // search for a bare pool code (`BRW`) also matches every one of its own
      // sub-locations (`BRW-AA`..`BRW-EE`) - a page of 5 can fill entirely with
      // those and never reach the pool row itself. Wide enough to cover a real
      // site's own sub-location count.
      pageSize: 50,
      sorting: [],
      searchQuery: location,
      is_active: true,
    })
      .then((response) => {
        if (cancelled) return;
        const match = (response.data ?? []).find(
          (warehouse) => warehouse.warehouse_code === location,
        );
        setResolved({ location, warehouse: match ?? null });
      })
      .catch(() => {
        if (!cancelled) setResolved({ location, warehouse: null });
      });
    return () => {
      cancelled = true;
    };
  }, [location]);

  const resolving = Boolean(location) && resolved?.location !== location;
  const warehouse = resolving ? null : (resolved?.warehouse ?? null);
  const suffixGroup = location ? groupOfWarehouseCode(location) : null;
  // A known bin is read by group only when it is a member of that group (in planning);
  // an unknown code keeps the suffix rule it had before.
  const group = warehouse ? (warehouse.fulfilment_planning ? suffixGroup : null) : suffixGroup;
  const warehouseId = group ? null : (warehouse?.id ?? null);

  // STOCK-STATUS round 6 (UAC AC-35): AutoCount's figures in the same table; a failed read
  // leaves today's.
  const autoCount = useStockStatus(productId, Boolean(location));
  const detail = useStockDetail(
    productId,
    warehouseId,
    lineIds,
    group,
    !resolving && Boolean(group || warehouseId),
  );

  // S1 fix round (22 Sep 2026): a `group` read tags every member location `where: "group"`
  // uniformly - the backend has no notion of "this is the ROW's own bin" in that shape,
  // since `group` mode answers for a whole ownership group, not one line. The row's own
  // bin is a fact THIS caller holds (`location`, the prop) and the board's other readers
  // do not need marked at all, so it is applied here, client-side, rather than asking the
  // endpoint to carry a per-caller opinion about which of its own rows is "home". Declared
  // above every early return - React's rules of hooks - even though it has nothing to do
  // until the "no location" / loading / error returns below have already passed.
  const locations = React.useMemo(() => {
    const raw = detail.data?.locations ?? [];
    if (!location) return raw;
    return raw.map((entry) =>
      entry.location === location ? { ...entry, where: 'own' as const } : entry,
    );
  }, [detail.data?.locations, location]);

  if (!location) {
    return (
      <p
        data-testid="oi-stock-grid-no-location"
        className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground"
      >
        No stock location on this row
      </p>
    );
  }

  if (resolving || detail.isLoading) {
    return (
      <div data-testid="oi-stock-grid-loading" className="space-y-2 py-1">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    );
  }

  if (detail.isError) {
    return (
      <p className="rounded-lg border border-destructive/30 px-3 py-2 text-xs text-destructive">
        {detail.error instanceof Error
          ? detail.error.message
          : 'The stock position could not be loaded.'}
      </p>
    );
  }

  return (
    <CellStockTable
      locations={locations}
      lineIds={lineIds}
      showGroupSubtotal
      autoCount={autoCount.data ?? null}
    />
  );
}

export default OrderInquiryStockGrid;
