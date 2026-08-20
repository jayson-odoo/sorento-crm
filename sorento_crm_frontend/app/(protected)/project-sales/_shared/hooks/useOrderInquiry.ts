'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  autoPlaceOrderInquiryRows,
  getOrderInquiryPoCandidates,
  getOrderInquiryPoDetail,
  getOrderInquirySummary,
  getOrderInquiryWorklistSummary,
  getSalesOrderInquiry,
  getUnplaceAllPreview,
  listOrderInquiryRows,
  listOrderInquiryWorklist,
  markOrderInquiryRows,
  placeOrderInquiryRowOnPo,
  placeOrderInquiryRowOnPoAllocations,
  unplaceAllOrderInquiryRows,
  unplaceOrderInquiryRow,
} from '../services/orderInquiryService';
import type {
  AutoPlaceRequest,
  OrderInquiryListParams,
  OrderInquiryPoAllocation,
  OrderInquiryWorklistParams,
  UnplaceAllRequest,
} from '../types/orderInquiry.types';

export const ORDER_INQUIRY_ROWS_KEY = 'project-order-inquiry-rows';
export const ORDER_INQUIRY_SUMMARY_KEY = 'project-order-inquiry-summary';
export const ORDER_INQUIRY_KEY = 'project-order-inquiry';
export const ORDER_INQUIRY_WORKLIST_KEY = 'order-inquiry-worklist';
export const ORDER_INQUIRY_WORKLIST_SUMMARY_KEY = 'order-inquiry-worklist-summary';
export const ORDER_INQUIRY_PO_CANDIDATES_KEY = 'order-inquiry-po-candidates';
export const ORDER_INQUIRY_PO_DETAIL_KEY = 'order-inquiry-po-detail';
export const ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY = 'order-inquiry-unplace-all-preview';

export const orderInquiryRowsKey = (
  projectId: string,
  params: OrderInquiryListParams,
) => [ORDER_INQUIRY_ROWS_KEY, projectId, params];

export function useOrderInquiryRows(
  projectId: string | undefined,
  params: OrderInquiryListParams = {},
) {
  return useQuery({
    queryKey: orderInquiryRowsKey(projectId ?? '', params),
    queryFn: () => listOrderInquiryRows(projectId as string, params),
    enabled: Boolean(projectId),
  });
}

export function useOrderInquirySummary(projectId: string | undefined) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_SUMMARY_KEY, projectId],
    queryFn: () => getOrderInquirySummary(projectId as string),
    enabled: Boolean(projectId),
  });
}

/**
 * Purchasing's own worklist: every raised row, across every project AND every adopted
 * AutoCount order, which belongs to no project and is therefore reachable nowhere else.
 *
 * `enabled` lets a caller hold the request off until it is actually needed - the
 * calendar view's day drilldown, for one, has nothing to ask for until a day is picked.
 */
export function useOrderInquiryWorklist(
  params: OrderInquiryWorklistParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_WORKLIST_KEY, params],
    queryFn: () => listOrderInquiryWorklist(params),
    enabled: options.enabled,
    // Every filter and every page is a new key, so without this the grid empties itself
    // between the press and the answer and the page jumps under the cursor.
    placeholderData: (previous) => previous,
  });
}

/**
 * The month strip and the state counts.
 *
 * Sent WITH the month filter, because the strip's totals are the visible month's. The
 * month AXIS (`by_month`) is the one thing the server computes ignoring that filter, so
 * the control that changes month never empties itself.
 */
export function useOrderInquiryWorklistSummary(
  params: OrderInquiryWorklistParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY, params],
    queryFn: () => getOrderInquiryWorklistSummary(params),
    enabled: options.enabled,
    // Above all here: the month strip is inside this answer, so without it pressing a
    // month makes the control you just used vanish until the next answer lands.
    placeholderData: (previous) => previous,
  });
}

/**
 * "Unplace all"'s own count for the toolbar button and its confirm dialog - the CURRENT
 * worklist scope (the SAME filters the list itself reads), resolved server-side so it is
 * right regardless of how many pages the matching set actually spans. Kept live the same
 * way the month strip is: it has to go to zero the instant the last placed row in scope
 * is dealt with, or the button stays clickable on an empty scope.
 */
export function useUnplaceAllPreview(
  filters: UnplaceAllRequest = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY, filters],
    queryFn: () => getUnplaceAllPreview(filters),
    enabled: options.enabled,
    placeholderData: (previous) => previous,
  });
}

export function useSalesOrderInquiry(psoId: string | undefined) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_KEY, psoId],
    queryFn: () => getSalesOrderInquiry(psoId as string),
    enabled: Boolean(psoId),
    // A sales order that has not published yet has no inquiry, and 404 is the honest
    // answer rather than a failure worth retrying.
    retry: false,
  });
}

/**
 * Marking rows refetches the rows AND the summary: the header count is the thing that
 * tells purchasing how much of this project is still open, and a stale one is worse than
 * no count at all.
 */
export function useOrderInquiryMutations(projectId: string) {
  const queryClient = useQueryClient();

  const mark = useMutation({
    mutationFn: ({ rowIds, state }: { rowIds: string[]; state: string }) =>
      markOrderInquiryRows(rowIds, state),
    onSuccess: (rows, variables) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      const count = rows.length;
      const said =
        variables.state === 'actioned'
          ? 'marked as actioned'
          : variables.state === 'cancelled'
            ? 'cancelled'
            : 'reopened';
      toast.success(`${count} row${count === 1 ? '' : 's'} ${said}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { mark };
}

/** Candidates for one row's "Place on PO" dialog (section G), fetched only while it is
 * open - `enabled` lets the caller hold the request off until the dialog mounts. */
export function useOrderInquiryPoCandidates(
  rowId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY, rowId],
    queryFn: () => getOrderInquiryPoCandidates(rowId as string),
    enabled: Boolean(rowId) && options.enabled !== false,
  });
}

/** The "PO no" cell's popup: that purchase order's header and every line, fetched only
 * while the popover is open - `enabled` holds the request off until then. */
export function useOrderInquiryPoDetail(
  poId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_PO_DETAIL_KEY, poId],
    queryFn: () => getOrderInquiryPoDetail(poId as string),
    enabled: Boolean(poId) && options.enabled !== false,
  });
}

/**
 * Place on PO / Unplace (section G). Not scoped to a project id: the per-project screen
 * and purchasing's cross-project worklist carry the same row action, so both invalidate
 * every query family a placement touches rather than just their own screen's.
 */
export function useOrderInquiryPlacementMutations() {
  const queryClient = useQueryClient();

  function invalidateAfterPlacement() {
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
    // Another raised row on the same product may now cover less (or more) of the PO
    // line this one just tagged or freed.
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
    // A single place/unplace moves the placed count "Unplace all" reads too.
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
  }

  const place = useMutation({
    mutationFn: ({ rowId, poLineId }: { rowId: string; poLineId: string }) =>
      placeOrderInquiryRowOnPo(rowId, poLineId),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Placed on the purchase order');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** The G2 cascade shape: one or more `{po_line_id, qty}` lines in one call. */
  const placeAllocations = useMutation({
    mutationFn: ({
      rowId,
      allocations,
    }: {
      rowId: string;
      allocations: OrderInquiryPoAllocation[];
    }) => placeOrderInquiryRowOnPoAllocations(rowId, allocations),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Placed on the purchase order');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const unplace = useMutation({
    mutationFn: (rowId: string) => unplaceOrderInquiryRow(rowId),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Unplaced');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { place, placeAllocations, unplace };
}

/**
 * Run the cascade now (G2 rule 4) - the worklist's "Auto-place". Invalidates the same
 * query families a single placement does, since a bulk pass can touch any of them.
 */
export function useAutoPlaceOrderInquiryRows() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: AutoPlaceRequest = {}) => autoPlaceOrderInquiryRows(params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
      toast.success(
        `${result.placed_rows} row${result.placed_rows === 1 ? '' : 's'} placed across ` +
          `${result.allocations} allocation${result.allocations === 1 ? '' : 's'}`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * "Unplace all" for the CURRENT worklist scope (the captain, 20-21 Aug): every PLACED
 * row matching the filters passed in reverts to raised, ready for a clean Auto-place
 * re-deal. Invalidates the same query families a single unplace does.
 */
export function useUnplaceAllOrderInquiryRows() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: UnplaceAllRequest = {}) => unplaceAllOrderInquiryRows(params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
      toast.success(
        `${result.unplaced} row${result.unplaced === 1 ? '' : 's'} unplaced`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
