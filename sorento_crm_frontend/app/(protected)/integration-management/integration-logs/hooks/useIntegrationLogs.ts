'use client';

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { getIntegrationLogs, getIntegrationLog, retryIntegrationLog, updateIntegrationLog } from '../services/integrationLogService';
import type { IntegrationLog, IntegrationLogResponse } from '../types/integrationLog.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export function useIntegrationLogs(params: DataGridApiFetchParams & {
  status?: string;
  integration_channel?: string;
  business_table?: string;
  business_id?: string;
  created_from?: string;
  created_to?: string;
  status_code?: string;
  error_contains?: string[];
}) {
  return useQuery<DataGridApiResponse<IntegrationLog>>({
    queryKey: ['integrationLogs', params],
    queryFn: () => getIntegrationLogs(params),
    placeholderData: keepPreviousData,
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
