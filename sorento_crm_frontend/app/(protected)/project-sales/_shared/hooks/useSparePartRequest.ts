'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { splitMulti } from '@/lib/list-filters/multiValue';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import { sparePartFilterStates } from '../lib/sparePartRequest';
import { toast } from '@/lib/toast';
import { codeWithName } from '@/lib/product-display';
import { searchStockVisibilityWarehouses } from '@/services/stockVisibilityService';
import {
  approveSparePartRequest,
  createSparePartRequest,
  editSparePartLine,
  getSparePartRequest,
  listSparePartRequests,
  rejectSparePartRequest,
  reviseSparePartRequest,
  submitSparePartRequest,
  updateSparePartRequest,
  type SparePartRequestInput,
  type SparePartRequestListParams,
} from '../services/sparePartRequestService';
import {
  ORDER_INQUIRY_HEADER_KEY,
  ORDER_INQUIRY_HEADER_LINES_KEY,
  ORDER_INQUIRY_HEADERS_KEY,
  ORDER_INQUIRY_HISTORY_KEY,
  ORDER_INQUIRY_WORKLIST_KEY,
} from './useOrderInquiry';

/**
 * SPARE-PART-ORDER-REQUEST: the request's own reads and moves. Every move refreshes the OI
 * page it opens on (header, lines, history) and the Order Inquiries list.
 */
export const SPARE_PART_REQUEST_KEY = 'spare-part-request';
/** G3: the requests' own list. */
export const SPARE_PART_REQUESTS_KEY = 'spare-part-requests';
const LOCATIONS_KEY = ['spare-part-request', 'locations'] as const;

export function useSparePartRequest(id: string | null | undefined) {
  return useQuery({
    queryKey: [SPARE_PART_REQUEST_KEY, id],
    queryFn: () => getSparePartRequest(id as string),
    enabled: Boolean(id),
  });
}

/** One key for the list and its record page's pager (`useListPager`), so both share a page. */
export function sparePartRequestsListQueryKey(params: SparePartRequestListParams) {
  return [
    SPARE_PART_REQUESTS_KEY,
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.states,
  ] as const;
}

/** The list query a record URL describes: the list writes its status filter as `status`. */
function sparePartRequestListParamsFromUrl(params: ListPagerParams): SparePartRequestListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    states: sparePartFilterStates(splitMulti(params.filters.status ?? '')),
  };
}

/** Prev / next on the record page, over the list page it was opened from. */
export const sparePartRequestsPagerQuery = {
  listQueryKey: (params: ListPagerParams) =>
    sparePartRequestsListQueryKey(sparePartRequestListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listSparePartRequests(sparePartRequestListParamsFromUrl(params)),
};

export function useSparePartRequests(params: SparePartRequestListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: sparePartRequestsListQueryKey(params),
    queryFn: () => listSparePartRequests(params),
  });
}

/** Active locations by code (a line's `stock_location` is the warehouse code), through the
 *  shared warehouse search every staff user can read. */
export function useSparePartLocations() {
  return useQuery({
    queryKey: LOCATIONS_KEY,
    queryFn: async () =>
      (await searchStockVisibilityWarehouses('')).map((w) => ({
        value: w.code,
        label: codeWithName(w.code, w.name),
      })),
    staleTime: 5 * 60_000,
  });
}

function useRefreshInquiry() {
  const qc = useQueryClient();
  return (id?: string) => {
    for (const key of [
      SPARE_PART_REQUEST_KEY,
      ORDER_INQUIRY_HEADER_KEY,
      ORDER_INQUIRY_HEADER_LINES_KEY,
      ORDER_INQUIRY_HISTORY_KEY,
    ]) {
      void qc.invalidateQueries({ queryKey: id ? [key, id] : [key] });
    }
    void qc.invalidateQueries({ queryKey: [ORDER_INQUIRY_HEADERS_KEY] });
    void qc.invalidateQueries({ queryKey: [SPARE_PART_REQUESTS_KEY] });
    void qc.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
  };
}

/** Save as draft: creates the request the first time, updates it after. No toast of its own
 *  on error: the form shows the message beside the field it names. */
export function useSaveSparePartRequest() {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string | null; body: SparePartRequestInput }) =>
      id ? updateSparePartRequest(id, body) : createSparePartRequest(body),
    onSuccess: (saved) => refresh(saved.id),
  });
}

export function useSubmitSparePartRequest() {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: (id: string) => submitSparePartRequest(id),
    onSuccess: (saved) => {
      refresh(saved.id);
      toast.success('Submitted for approval');
    },
  });
}

export function useEditSparePartLine(id: string) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: ({ rowId, edit }: { rowId: string; edit: { qty?: string; unit_price?: string } }) =>
      editSparePartLine(id, rowId, edit),
    onSuccess: () => refresh(id),
    onError: (e: Error) => toast.error(e.message),
  });
}

/** `submittedAt`: the submission the page rendered, so a stale page's decision is refused. */
export function useApproveSparePartRequest(id: string, submittedAt?: string | null) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: (note?: string) => approveSparePartRequest(id, note, submittedAt),
    onSuccess: (saved) => {
      refresh(id);
      // Final only when raised with no revision still waiting (a revision's next level).
      const final = saved.state === 'raised' && !saved.revision_state;
      toast.success(final ? 'Approved and sent to purchasing' : 'Approved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRejectSparePartRequest(id: string, submittedAt?: string | null) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: (reason: string) => rejectSparePartRequest(id, reason, submittedAt),
    onSuccess: () => {
      refresh(id);
      toast.success('Rejected');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useReviseSparePartRequest(id: string) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: () => reviseSparePartRequest(id),
    onSuccess: () => {
      refresh(id);
      toast.success('Back to draft');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
