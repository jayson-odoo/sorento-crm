'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fmtQty } from '../lib/qtyPrecision';
import { confirmDecisions } from '../services/decisionService';
import {
  getOrderSummary,
  getOrderSummaryDemand,
  getOrderSummaryLocations,
  getOrderSummarySuppliers,
  recordOrderDecision,
  type OrderSummaryQuery,
} from '../services/summaryOrderService';
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDemandKind,
} from '../types/summaryOrder.types';

/** Prefix key for the Purchase Orders list - invalidated whenever a draft PO changes
 *  (mirrors `useDecisions.ts`'s own copy for the location-grain confirm). */
const purchaseOrdersKey = ['scm', 'purchase-orders'];

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

/**
 * The member locations behind one product row (AC-F08).
 *
 * Lazy on the drill's own open flag, like the demand drills: a report of three
 * thousand products must not fetch a location breakdown per row to render.
 */
export function useOrderSummaryLocations(
  productCode: string | null,
  runId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'reorder', 'order-summary-locations', runId, productCode] as const,
    queryFn: () => getOrderSummaryLocations(productCode as string, runId),
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
 *
 * The toast renders the quantity at the ROW'S frozen `uom_decimal_places`
 * (AC-F12), which is why the caller passes it: an integer format read back an
 * accepted `2.75 kg` as "3", so the confirmation disagreed with the decision it
 * was confirming. The response carries no precision of its own - the frozen one
 * belongs to the row the sheet was opened on.
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
      decimalPlaces?: number | null;
    }) => recordOrderDecision(productCode, input),
    onSuccess: (result, variables) => {
      void qc.invalidateQueries({ queryKey: orderSummaryKey(q) });
      // The chosen quantity re-splits across locations, so the drill that shows the
      // split has to be re-read or it keeps describing the previous decision.
      void qc.invalidateQueries({ queryKey: ['scm', 'reorder', 'order-summary-locations'] });
      toast.success(
        `${result.product_code} - ordering ${fmtQty(
          result.chosen_qty,
          variables.decimalPlaces ?? 0,
        )} from ${result.chosen_supplier_name}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/**
 * Confirm decisions on a PRODUCT-grain run (captain, 21 Aug): materialises every
 * decided row's `chosen_qty` into a consolidated draft PO, exactly the way the
 * location-grain "buy" tab's own confirm does (`useDecisions.ts`'s `confirm`) - same
 * endpoint, same result shape, the service dispatches on the run's stamped grain.
 *
 * Invalidates the report (so a re-confirm's reconciled qty is visible) and the
 * Purchase Orders list (so the freshly-drafted PO appears there).
 */
export function useConfirmOrderDecisions(runId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => {
      if (!runId) return Promise.reject(new Error('No plan is open to confirm decisions on.'));
      return confirmDecisions(runId);
    },
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: orderSummaryKey({ run_id: runId }) });
      void qc.invalidateQueries({ queryKey: purchaseOrdersKey });
      toast.success(
        result.confirmed_count > 0
          ? `Confirmed ${result.confirmed_count} decision${
              result.confirmed_count === 1 ? '' : 's'
            } into ${result.po_count} draft purchase order${result.po_count === 1 ? '' : 's'}`
          : 'Nothing to confirm - no order quantity has been decided yet',
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
