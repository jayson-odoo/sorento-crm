import { apiFetch } from '@/lib/api';
import type { ImportJob } from '../types/importJob.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getImportJobs(
  params: DataGridApiFetchParams & { job_type?: string; status?: string },
): Promise<DataGridApiResponse<ImportJob>> {
  const { pageIndex, pageSize, job_type, status } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(job_type ? { job_type } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/v1/system/jobs?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch import jobs');
  return response.json();
}

export async function getImportJob(jobId: string): Promise<ImportJob> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}`);
  if (!response.ok) throw new Error('Failed to fetch import job');
  return response.json();
}

export async function getImportJobStatus(jobId: string): Promise<{
  job_id: string;
  status: string;
  progress?: {
    total: number;
    processed: number;
    successful: number;
    failed: number;
    skipped: number;
    percentage: number;
  };
  result?: any;
  error?: string | null;
}> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/status`);
  if (!response.ok) throw new Error('Failed to fetch job status');
  return response.json();
}

export async function getImportJobSourceUrl(
  jobId: string,
): Promise<{ url: string; filename?: string | null; size?: number | null }> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/source`);
  if (!response.ok) throw new Error('Failed to fetch source file link');
  return response.json();
}

export async function cancelImportJob(jobId: string): Promise<{ message: string }> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to cancel import job' }));
    throw new Error(error.detail || 'Failed to cancel import job');
  }
  return response.json();
}
