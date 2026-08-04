'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getOrderSummary,
  getOrderSummaryDemand,
  getOrderSummarySuppliers,
  recordOrderDecision,
  type OrderSummaryQuery,
} from '../services/summaryOrderService';
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDemandKind,
} from '../types/summaryOrder.types';

/** Query key for one week's report. Exported so a decision can bust it. */
export function orderSummaryKey(q: OrderSummaryQuery = {}) {
  return ['scm', 'reorder', 'order-summary', q.run_id ?? null] as const;
}

/**
 * The Summary Order Report (AC-C2.1).
 *
 * Keyed on run plus as-of date, because a past week must come back as it was
 * rather than as a recomputation against today's book (AC-C2.9). A frozen report
 * cannot change under the reader, so it caches for the length of a sitting.
 */
export function useOrderSummary(q: OrderSummaryQuery = {}, enabled = true) {
  return useQuery({
    queryKey: orderSummaryKey(q),
    queryFn: () => getOrderSummary(q),
    enabled,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * The lines behind one aggregate (AC-C2.3 / AC-C2.4).
 *
 * Lazy: `enabled` is the information icon's own open flag, so opening the report
 * does not fetch two drills per row.
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
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** The supplier candidates for one product (AC-C2.5). Lazy on the decision sheet. */
export function useOrderSummarySuppliers(productCode: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'order-summary-suppliers', productCode] as const,
    queryFn: () => getOrderSummarySuppliers(productCode as string),
    enabled: enabled && !!productCode,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * Record the chosen quantity and supplier (AC-C2.8).
 *
 * A quantity above the shortfall is a normal decision, so the success toast
 * states what was recorded and never cautions about the size of it.
 */
export function useRecordOrderDecision(q: OrderSummaryQuery = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      productCode,
      input,
    }: {
      productCode: string;
      input: OrderSummaryDecisionInput;
    }) => recordOrderDecision(productCode, input),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: orderSummaryKey(q) });
      toast.success(
        `${result.product_code} - ordering ${result.chosen_qty.toLocaleString('en-MY')} from ${result.chosen_supplier_name}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
