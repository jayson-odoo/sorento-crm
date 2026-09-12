'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { ENTITY_DOWNLOADS_QUERY_KEY, MY_DOWNLOADS_QUERY_KEY } from '@/services/myDownloadsService';
import { exportOrderSheet, getOrderSummaryDemand } from '../services/summaryOrderService';
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

/**
 * The order sheet, through My Downloads (S4, AC-19/AC-20/AC-21). Starts the export and
 * refreshes both surfaces that show it: the top-nav drawer's per-user feed and this run's
 * own entity-downloads chip. The sheet itself is fetched later from My Downloads, once the
 * worker marks the row ready - this mutation never returns or saves a file.
 */
export function useExportOrderSheet(runId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (format: 'pdf' | 'xlsx') => exportOrderSheet(runId as string, format),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({
        queryKey: [...ENTITY_DOWNLOADS_QUERY_KEY, 'reorder_run', runId],
      });
      toast.success('Preparing the order sheet - it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start the order sheet export'),
  });
}
