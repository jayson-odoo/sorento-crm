'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { codeWithName } from '@/lib/product-display';
import { searchStockVisibilityWarehouses } from '@/services/stockVisibilityService';
import {
  approveSparePartRequest,
  createSparePartRequest,
  editSparePartLine,
  getSparePartRequest,
  rejectSparePartRequest,
  reviseSparePartRequest,
  submitSparePartRequest,
  updateSparePartRequest,
  type SparePartRequestInput,
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
const LOCATIONS_KEY = ['spare-part-request', 'locations'] as const;

export function useSparePartRequest(id: string | null | undefined) {
  return useQuery({
    queryKey: [SPARE_PART_REQUEST_KEY, id],
    queryFn: () => getSparePartRequest(id as string),
    enabled: Boolean(id),
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

export function useApproveSparePartRequest(id: string) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: (note?: string) => approveSparePartRequest(id, note),
    onSuccess: (saved) => {
      refresh(id);
      toast.success(saved.state === 'raised' ? 'Approved and sent to purchasing' : 'Approved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRejectSparePartRequest(id: string) {
  const refresh = useRefreshInquiry();
  return useMutation({
    mutationFn: (reason: string) => rejectSparePartRequest(id, reason),
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
