import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getImportJobs, getImportJob, getImportJobStatus } from '../services/importJobService';

export function useImportJobs(params: DataGridApiFetchParams & { job_type?: string; status?: string }) {
  return useQuery({
    queryKey: ['import-jobs', params.pageIndex, params.pageSize, params.job_type, params.status],
    queryFn: () => getImportJobs(params),
    staleTime: 1000 * 30, // 30 seconds - jobs update frequently
    refetchOnWindowFocus: true,
    retry: 1,
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
