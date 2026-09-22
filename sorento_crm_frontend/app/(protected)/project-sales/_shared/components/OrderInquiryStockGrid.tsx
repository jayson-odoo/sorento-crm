'use client';

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import { CellStockTable } from '../../fulfilment-planning/components/CellStockTable';
import { useStockDetail } from '../hooks/useFulfilmentPlanning';
import { groupOfWarehouseCode } from '../lib/supplyVocabulary';

/**
 * The board's own stock position, on the OI Lines tab and the reserve dialog/card
 * (`PLAN-oi-request-cs-reserve.md` 3.9, AC-RS-40/41).
 *
 * A thin wrapper, deliberately: `CellStockTable` already draws the matrix, the group
 * subtotal and the expandable documents panel (each row's own chevron opens
 * `StockDocumentsPanel` internally) - what this component adds is turning a ROW's
 * location CODE into the `group` or `warehouse_id` `stock-detail` wants, the same rule
 * the board's own cells resolve by (`group_of_warehouse_code`, spelled once and shared
 * as `groupOfWarehouseCode`).
 *
 * `BRW-BB` -> the ownership-group suffix `BB`. A bare pool code (`BRW`, no hyphen) names
 * no group - it IS a pool - so it resolves to ITS OWN `warehouse_id` first, via
 * `getWarehouses` (the only warehouse-list fetcher that carries `id`; `warehouseSelectService`
 * keys by CODE, which `stock-detail` cannot take). `useStockDetail`'s own `enabled` gate
 * stays off until that resolution lands, so no request goes out asking for neither a group
 * nor a warehouse (the route 422s on that).
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
  const group = React.useMemo(
    () => (location ? groupOfWarehouseCode(location) : null),
    [location],
  );
  const isBarePoolCode = Boolean(location) && !group;

  const [resolvedWarehouseId, setResolvedWarehouseId] = React.useState<string | null>(null);
  const [resolving, setResolving] = React.useState(isBarePoolCode);

  React.useEffect(() => {
    if (!isBarePoolCode || !location) {
      setResolvedWarehouseId(null);
      setResolving(false);
      return;
    }
    let cancelled = false;
    setResolving(true);
    getWarehouses({
      pageIndex: 0,
      pageSize: 5,
      sorting: [],
      searchQuery: location,
      is_active: true,
    })
      .then((response) => {
        if (cancelled) return;
        const match = (response.data ?? []).find(
          (warehouse) => warehouse.warehouse_code === location,
        );
        setResolvedWarehouseId(match?.id ?? null);
      })
      .finally(() => {
        if (!cancelled) setResolving(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isBarePoolCode, location]);

  const warehouseId = isBarePoolCode ? resolvedWarehouseId : null;
  const detail = useStockDetail(
    productId,
    warehouseId,
    lineIds,
    group,
    !isBarePoolCode || Boolean(resolvedWarehouseId),
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

  return <CellStockTable locations={locations} lineIds={lineIds} showGroupSubtotal />;
}

export default OrderInquiryStockGrid;
