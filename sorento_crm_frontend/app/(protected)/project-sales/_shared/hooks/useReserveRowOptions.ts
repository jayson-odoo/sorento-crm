'use client';

import * as React from 'react';
import { useQueries } from '@tanstack/react-query';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { STOCK_DETAIL_KEY } from './useFulfilmentPlanning';
import { getStockDetail } from '../services/fulfilmentPlanningService';
import { groupOfWarehouseCode } from '../lib/supplyVocabulary';

/**
 * `PLAN-oi-request-cs-reserve.md` 3.7/3.8: the reserve dialog's own "default = the pool,
 * options = the row's stock-grid locations" (AC-RS-22) and the act-mode card's "default
 * Reserved = min(requested, available at that location)" (AC-RS-26) - ONE resolution,
 * shared by both callers, so the pool default and the stock-grid options can never read
 * two different answers for the same row.
 *
 * MEASURED against the real stack (22 Sep 2026, `stock-detail?group=IB`): a GROUP read
 * answers for that group's OWN members only (`BRW-IB`, `DC1-IB`, ...) - the site POOL
 * itself (bare `BRW`) is a DIFFERENT axis (`group=pools`) and is simply absent from a
 * named group's own response. So the pool's id is ALWAYS resolved the one-shot way
 * `OrderInquiryStockGrid` already resolves a bare pool code (`getWarehouses`, matching by
 * the SITE prefix) - never read off the group response - and offered as its own option
 * alongside whichever group members that response carries. A row already at a bare pool
 * code (no group suffix - it IS one) needs no second call for its own row: the pool
 * resolution IS its only option.
 */

function siteCodeOf(code: string | null | undefined): string | null {
  if (!code) return null;
  const cut = code.indexOf('-');
  return cut < 0 ? code : code.slice(0, cut);
}

export interface ReserveRowOptionsEntry {
  key: string;
  productId: string | null;
  /** The row's own stock location code (`BRW-NTC`), or null when the row states none. */
  location: string | null;
}

export interface ReserveRowOptionsResult {
  isLoading: boolean;
  defaultWarehouseId: string | null;
  options: SearchableSelectOption[];
  /** `available_qty` at every resolved warehouse id this row's own grid carries - the
   * act-mode card's own "Reserved" default reads this at the CHOSEN location, which may
   * move away from the default once the reader changes it (AC-RS-28). */
  availableQtyByWarehouseId: Record<string, number>;
}

const EMPTY_RESULT: ReserveRowOptionsResult = {
  isLoading: false,
  defaultWarehouseId: null,
  options: [],
  availableQtyByWarehouseId: {},
};

export function useReserveRowOptions(
  entries: ReserveRowOptionsEntry[],
): Record<string, ReserveRowOptionsResult> {
  const siteCodes = React.useMemo(
    () =>
      Array.from(
        new Set(
          entries
            .map((entry) => siteCodeOf(entry.location))
            .filter((code): code is string => Boolean(code)),
        ),
      ),
    [entries],
  );
  const siteCodesKey = siteCodes.join(',');
  const [resolvedPoolIds, setResolvedPoolIds] = React.useState<Record<string, string | null>>({});

  React.useEffect(() => {
    const codes = siteCodesKey ? siteCodesKey.split(',') : [];
    const unresolved = codes.filter((code) => !(code in resolvedPoolIds));
    if (unresolved.length === 0) return;
    let cancelled = false;
    Promise.all(
      unresolved.map((code) =>
        getWarehouses({
          pageIndex: 0,
          pageSize: 5,
          sorting: [],
          searchQuery: code,
          is_active: true,
        }).then(
          (response) =>
            [code, (response.data ?? []).find((w) => w.warehouse_code === code)?.id ?? null] as const,
        ),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setResolvedPoolIds((prev) => {
        const next = { ...prev };
        for (const [code, id] of pairs) next[code] = id;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCodesKey]);

  const groupQueries = useQueries({
    queries: entries.map((entry) => {
      const group = entry.location ? groupOfWarehouseCode(entry.location) : null;
      return {
        queryKey: [STOCK_DETAIL_KEY, entry.productId, group, 'reserve-options-group'],
        queryFn: () => getStockDetail(entry.productId as string, null, [], group),
        enabled: Boolean(entry.productId) && Boolean(group),
      };
    }),
  });

  // The site's own POOL is a one-bin read of its own - a GROUP response never carries it
  // (measured against the real stack, see the module docstring), so its own `available_
  // qty` needs its own call once the pool's id has resolved.
  const poolQueries = useQueries({
    queries: entries.map((entry) => {
      const siteCode = siteCodeOf(entry.location);
      const poolId = siteCode ? resolvedPoolIds[siteCode] ?? null : null;
      return {
        queryKey: [STOCK_DETAIL_KEY, entry.productId, poolId, 'reserve-options-pool'],
        queryFn: () => getStockDetail(entry.productId as string, poolId, [], null),
        enabled: Boolean(entry.productId) && Boolean(poolId),
      };
    }),
  });

  const result: Record<string, ReserveRowOptionsResult> = {};
  entries.forEach((entry, index) => {
    if (!entry.location || !entry.productId) {
      result[entry.key] = EMPTY_RESULT;
      return;
    }
    const siteCode = siteCodeOf(entry.location) as string;
    const poolId = resolvedPoolIds[siteCode] ?? null;
    const group = groupOfWarehouseCode(entry.location);
    const groupQuery = group ? groupQueries[index] : null;
    const groupLocations = groupQuery?.data?.locations ?? [];
    const poolQuery = poolId ? poolQueries[index] : null;

    const availableQtyByWarehouseId: Record<string, number> = {};
    const options: SearchableSelectOption[] = [];
    if (poolId) {
      options.push({ value: poolId, label: siteCode });
      if (poolQuery?.data?.available_qty != null) {
        availableQtyByWarehouseId[poolId] = Number(poolQuery.data.available_qty);
      }
    }
    for (const loc of groupLocations) {
      if (!loc.warehouse_id || loc.warehouse_id === poolId) continue;
      options.push({ value: loc.warehouse_id, label: loc.location ?? '' });
      if (loc.available_qty != null) {
        availableQtyByWarehouseId[loc.warehouse_id] = Number(loc.available_qty);
      }
    }

    result[entry.key] = {
      isLoading: Boolean(groupQuery?.isLoading) || Boolean(poolQuery?.isLoading),
      defaultWarehouseId: poolId ?? options[0]?.value ?? null,
      options,
      availableQtyByWarehouseId,
    };
  });
  return result;
}
