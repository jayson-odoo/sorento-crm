'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  cancelQuotationInAutocount,
  cancelSalesOrderInAutocount,
  createSalesOrderInAutocount,
  getAutocountWriteCapabilities,
  getAutocountWriteSwitch,
  sendQuotationToAutocount,
  updateSalesOrderInAutocount,
} from '../services/projectAutocountWriteService';
import type { AutocountWriteResult } from '../types/projectAutocountWrite.types';

export const AUTOCOUNT_WRITE_PERMISSION = 'projects.autocount.write';
const SWITCH_KEY = ['system-app-config', 'project-autocount-write'];
const CAPABILITIES_KEY = ['project-autocount-write', 'capabilities'];

/**
 * Whether any AutoCount write action may render: the admin switch is on AND the user holds the
 * permission. Off, nothing renders at all (U2), not even a greyed ghost.
 */
export function useAutocountWriteAccess(): boolean {
  const permitted = useHasPermission(AUTOCOUNT_WRITE_PERMISSION);
  const { data } = useQuery({
    queryKey: SWITCH_KEY,
    queryFn: getAutocountWriteSwitch,
    staleTime: 60_000,
    retry: false,
  });
  return Boolean(permitted && data);
}

/** The Shared Service's feed, read when the actions show; never hard-coded. */
export function useAutocountWriteCapabilities(enabled: boolean) {
  return useQuery({
    queryKey: CAPABILITIES_KEY,
    queryFn: getAutocountWriteCapabilities,
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * One write action. The answer (done, refused, pending, unreachable) goes to the caller's
 * dialog; only a CRM refusal reaches the toast. A `done` answer refreshes what the screen shows.
 */
function useAutocountWrite(
  run: (id: string) => Promise<AutocountWriteResult>,
  invalidate: (queryClient: ReturnType<typeof useQueryClient>) => void,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (result) => {
      if (result.outcome === 'done') invalidate(queryClient);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

const refreshOrders = (queryClient: ReturnType<typeof useQueryClient>) => {
  queryClient.invalidateQueries({ queryKey: ['project-sales-orders'] });
  queryClient.invalidateQueries({ queryKey: ['project-sales-order'] });
  queryClient.invalidateQueries({ queryKey: ['project-sales-order-worksheet'] });
};

const refreshQuotations = (queryClient: ReturnType<typeof useQueryClient>) => {
  queryClient.invalidateQueries({ queryKey: ['project-quotation-documents'] });
};

export const useCreateSalesOrderInAutocount = () =>
  useAutocountWrite(createSalesOrderInAutocount, refreshOrders);
export const useUpdateSalesOrderInAutocount = () =>
  useAutocountWrite(updateSalesOrderInAutocount, refreshOrders);
export const useCancelSalesOrderInAutocount = () =>
  useAutocountWrite(cancelSalesOrderInAutocount, refreshOrders);
export const useSendQuotationToAutocount = () =>
  useAutocountWrite(sendQuotationToAutocount, refreshQuotations);
export const useCancelQuotationInAutocount = () =>
  useAutocountWrite(cancelQuotationInAutocount, refreshQuotations);
