'use client';

import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { getIntegrationLogs, getIntegrationLog, retryIntegrationLog, updateIntegrationLog } from '../services/integrationLogService';
import type { IntegrationLog, IntegrationLogResponse } from '../types/integrationLog.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export type IntegrationLogsListParams = DataGridApiFetchParams & {
  status?: string;
  integration_channel?: string;
  business_table?: string;
  business_id?: string;
  created_from?: string;
  created_to?: string;
  status_code?: string;
  error_contains?: string[];
};

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function integrationLogsListQueryKey(
  params: IntegrationLogsListParams,
): QueryKey {
  return ['integrationLogs', params];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function integrationLogsListParamsFromUrl(
  params: ListPagerParams,
): IntegrationLogsListParams {
  const f = params.filters;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: f.status,
    integration_channel: f.integration_channel,
    business_table: f.business_table,
    created_from: f.created_from,
    created_to: f.created_to,
    status_code: f.status_code,
    error_contains: f.error_contains ? f.error_contains.split(',') : undefined,
  };
}

/** The pager's two hooks into the integration logs list. */
export const integrationLogsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    integrationLogsListQueryKey(integrationLogsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getIntegrationLogs(integrationLogsListParamsFromUrl(params)),
};

export function useIntegrationLogs(params: IntegrationLogsListParams) {
  return useQuery<DataGridApiResponse<IntegrationLog>>({
    ...LIST_QUERY_OPTIONS,
    queryKey: integrationLogsListQueryKey(params),
    queryFn: () => getIntegrationLogs(params),
  });
}

export function useIntegrationLog(id: string) {
  return useQuery<IntegrationLogResponse>({
    queryKey: ['integrationLog', id],
    queryFn: () => getIntegrationLog(id),
    enabled: !!id,
  });
}

export function useRetryIntegrationLog() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id: string) => retryIntegrationLog(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['integrationLogs'] });
      queryClient.invalidateQueries({ queryKey: ['integrationLog', data.id] });
    },
  });
}

export function useUpdateIntegrationLog() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { status: string; status_code?: number; response_payload?: string; error_code?: string; error_message?: string } }) => 
      updateIntegrationLog(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['integrationLogs'] });
      queryClient.invalidateQueries({ queryKey: ['integrationLog', data.id] });
    },
  });
}
