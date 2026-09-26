'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { ExportSplit } from '@/components/common/export-split';
import { ENTITY_DOWNLOADS_QUERY_KEY, MY_DOWNLOADS_QUERY_KEY } from '@/services/myDownloadsService';
import {
  exportLowStockReport,
  exportOiWorksheet,
  exportOrderSheet,
  getLowStockPreview,
  getOrderSummaryDemand,
} from '../services/summaryOrderService';
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

/**
 * The low stock report, through the same My Downloads pipeline (PLAN-low-stock-report S4,
 * AC-2; split added PLAN-low-stock-export-split-25sep AC-17). Its own mutation rather than
 * a third `format` on `useExportOrderSheet`, so the two report kinds carry their own toast
 * and their own pending flag - and so a reader of the Actions menu can tell which of the
 * two is in flight. The split chosen in `LowStockExportDialog` is the mutation variable.
 */
export function useExportLowStockReport(runId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (split: ExportSplit) => exportLowStockReport(runId as string, split),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({
        queryKey: [...ENTITY_DOWNLOADS_QUERY_KEY, 'reorder_run', runId],
      });
      toast.success('Preparing the low stock report - it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start the low stock report'),
  });
}

/**
 * The split dialog's own "N rows, M sheets" preview (R4, AC-15b/AC-16b): fetched once when
 * the dialog opens (`enabled` is the dialog's own `open` flag), never on page load and
 * never refetched on a radio change - `previewLowStockExport` recomputes the sheet count
 * locally. `staleTime: 0` so a stale plan (rows changed since the last open) is not shown
 * as fresh; `retry: false` so a failed read surfaces promptly and the dialog can hide the
 * line rather than spin.
 */
export function useLowStockPreview(runId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'order-summary', 'low-stock-preview', runId] as const,
    queryFn: () => getLowStockPreview(runId as string),
    enabled: !!runId && enabled,
    staleTime: 0,
    retry: false,
  });
}

/**
 * The OI worksheet, through the same My Downloads pipeline (Lane C, PLAN-order-sheet-oi-
 * reports-22sep.md, AC-C1/AC-C2). Its own mutation, the same shape as
 * `useExportLowStockReport` - so the plan's Actions menu can tell which of the three
 * exports is in flight and toast the worksheet's own message.
 */
export function useExportOiWorksheet(runId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => exportOiWorksheet(runId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({
        queryKey: [...ENTITY_DOWNLOADS_QUERY_KEY, 'reorder_run', runId],
      });
      toast.success('Preparing the OI worksheet - it will appear in My Downloads.');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start the OI worksheet export'),
  });
}
