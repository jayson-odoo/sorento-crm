'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useHasPermission } from '@/hooks/usePermissions';
import { DOCUMENTS_KEY } from './useQuotationDocuments';
import {
  SALES_ORDERS_KEY,
  SALES_ORDER_KEY,
  SALES_ORDER_WORKSHEET_KEY,
} from './useProjectSalesOrders';
import {
  cancelQuotationInAutocount,
  cancelSalesOrderInAutocount,
  createSalesOrderInAutocount,
  getAutocountRegisterSwitch,
  getAutocountWriteCapabilities,
  getAutocountWriteSwitch,
  getProjectAutocountRegister,
  registerProjectInAutocount,
  sendQuotationToAutocount,
  updateSalesOrderInAutocount,
} from '../services/projectAutocountWriteService';
import type { AutocountWriteResult } from '../types/projectAutocountWrite.types';

export const AUTOCOUNT_WRITE_PERMISSION = 'projects.autocount.write';
const SWITCH_KEY = ['system-app-config', 'project-autocount-write'];
const CAPABILITIES_KEY = ['project-autocount-write', 'capabilities'];
const REGISTER_SWITCH_KEY = ['system-app-config', 'project-autocount-register'];
const REGISTER_KEY = 'project-autocount-register';
// The prefix of `projectKey` in useProjects (['projects', 'detail', id]), spelled here so this
// file does not import the project hooks.
const PROJECT_DETAIL_KEY = ['projects', 'detail'];

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

/**
 * AC-PROJECT-REGISTER: whether "Register in AutoCount" may render. Its own admin switch AND the
 * same permission. Without the permission the switch is not even read (R18).
 */
export function useAutocountRegisterAccess(): boolean {
  const permitted = useHasPermission(AUTOCOUNT_WRITE_PERMISSION);
  const { data } = useQuery({
    queryKey: REGISTER_SWITCH_KEY,
    queryFn: getAutocountRegisterSwitch,
    enabled: permitted,
    staleTime: 60_000,
    retry: false,
  });
  return Boolean(permitted && data);
}

/** Whether this project can be registered now; read only when the item may show. */
export function useProjectAutocountRegister(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: [REGISTER_KEY, projectId],
    queryFn: () => getProjectAutocountRegister(projectId),
    enabled: enabled && Boolean(projectId),
    staleTime: 30_000,
    retry: false,
  });
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
  queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY] });
  queryClient.invalidateQueries({ queryKey: [SALES_ORDER_KEY] });
  queryClient.invalidateQueries({ queryKey: [SALES_ORDER_WORKSHEET_KEY] });
};

const refreshQuotations = (queryClient: ReturnType<typeof useQueryClient>) => {
  queryClient.invalidateQueries({ queryKey: [DOCUMENTS_KEY] });
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

const refreshProject = (queryClient: ReturnType<typeof useQueryClient>) => {
  queryClient.invalidateQueries({ queryKey: PROJECT_DETAIL_KEY });
  queryClient.invalidateQueries({ queryKey: [REGISTER_KEY] });
};

export const useRegisterProjectInAutocount = () =>
  useAutocountWrite(registerProjectInAutocount, refreshProject);
