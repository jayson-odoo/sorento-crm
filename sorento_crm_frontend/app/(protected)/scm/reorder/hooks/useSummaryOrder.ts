'use client';

import { useQuery } from '@tanstack/react-query';
import { getOrderSummaryDemand } from '../services/summaryOrderService';
import type { OrderSummaryDemandKind } from '../types/summaryOrder.types';

/**
 * The lines behind one aggregate (AC-C2.3 / AC-C2.4).
 *
 * Lazy: `enabled` is the information icon's own open flag, so opening the report
 * does not fetch two drills per row.
 *
 * The other hooks this file used to carry (`useOrderSummary`, `useOrderSummaryLocations`,
 * `useOrderSummarySuppliers`, `useRecordOrderDecision`, `useConfirmOrderDecisions`) were
 * the Order summary report page's own reads/writes - retired with that page (S10, round
 * 2, 9 Sep: the sheet now prints straight off the plan's Actions menu). This one survives
 * because `DemandDrillPopover` still opens it from the plan grid.
 */
export function useOrderSummaryDemand(
  productCode: string | null,
  kind: OrderSummaryDemandKind,
  runId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'order-summary-demand', runId, productCode, kind] as const,
    queryFn: () => getOrderSummaryDemand(productCode as string, kind, runId),
    enabled: enabled && !!productCode,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}
