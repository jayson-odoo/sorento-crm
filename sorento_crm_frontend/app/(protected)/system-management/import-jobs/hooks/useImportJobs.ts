import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getImportJobs,
  getImportJob,
  getImportJobStatus,
  getImportJobRows,
  cancelImportJob,
} from '../services/importJobService';
import type { ImportJobRowsQuery } from '../types/importJob.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useImportJobs(params: DataGridApiFetchParams & { job_type?: string; status?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['import-jobs', params.pageIndex, params.pageSize, params.job_type, params.status],
    queryFn: () => getImportJobs(params),
    staleTime: 1000 * 30, // 30 seconds - jobs update frequently
    refetchOnWindowFocus: true,
    retry: 1,
    refetchInterval: (query) => {
      const data = query.state.data?.data;
      const hasInProgress = data?.some((j: { status: string }) =>
        ['pending', 'queued', 'started'].includes(j.status),
      );
      return hasInProgress ? 2000 : false; // Poll every 2s when any job is in progress
    },
  });
}

export function useImportJob(jobId: string) {
  return useQuery({
    queryKey: ['import-job', jobId],
    queryFn: () => getImportJob(jobId),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}

export function useImportJobStatus(jobId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ['import-job-status', jobId],
    queryFn: () => getImportJobStatus(jobId),
    enabled,
    staleTime: 1000 * 5, // 5 seconds - status updates frequently
    refetchInterval: (query) => {
      const data = query.state.data;
      // Poll every 2 seconds if job is still processing
      if (data && ['pending', 'queued', 'started'].includes(data.status)) {
        return 2000;
      }
      return false; // Stop polling if finished/failed
    },
    refetchOnWindowFocus: true,
    retry: 1,
  });
}

export function useImportJobRows(jobId: string, params: ImportJobRowsQuery, enabled = true) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'import-job-rows',
      jobId,
      params.pageIndex,
      params.pageSize,
      params.outcome,
      params.code,
      params.query,
    ],
    queryFn: () => getImportJobRows(jobId, params),
    enabled: enabled && Boolean(jobId),
    staleTime: 1000 * 60,
    retry: 1,
  });
}

export function useCancelImportJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => cancelImportJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
      queryClient.invalidateQueries({ queryKey: ['import-job', jobId] });
      queryClient.invalidateQueries({ queryKey: ['import-job-status', jobId] });
    },
  });
}
