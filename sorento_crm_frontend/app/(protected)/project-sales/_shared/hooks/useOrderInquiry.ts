'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getOrderInquirySummary,
  getOrderInquiryWorklistSummary,
  getSalesOrderInquiry,
  listOrderInquiryRows,
  listOrderInquiryWorklist,
  markOrderInquiryRows,
} from '../services/orderInquiryService';
import type {
  OrderInquiryListParams,
  OrderInquiryWorklistParams,
} from '../types/orderInquiry.types';

export const ORDER_INQUIRY_ROWS_KEY = 'project-order-inquiry-rows';
export const ORDER_INQUIRY_SUMMARY_KEY = 'project-order-inquiry-summary';
export const ORDER_INQUIRY_KEY = 'project-order-inquiry';
export const ORDER_INQUIRY_WORKLIST_KEY = 'order-inquiry-worklist';
export const ORDER_INQUIRY_WORKLIST_SUMMARY_KEY = 'order-inquiry-worklist-summary';

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
 */
export function useOrderInquiryWorklist(params: OrderInquiryWorklistParams = {}) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_WORKLIST_KEY, params],
    queryFn: () => listOrderInquiryWorklist(params),
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
export function useOrderInquiryWorklistSummary(params: OrderInquiryWorklistParams = {}) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY, params],
    queryFn: () => getOrderInquiryWorklistSummary(params),
    // Above all here: the month strip is inside this answer, so without it pressing a
    // month makes the control you just used vanish until the next answer lands.
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
