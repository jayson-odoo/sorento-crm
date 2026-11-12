import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  ConfirmJobValues,
  DispatchBoard,
  ServiceJob,
  TransitionValues,
} from '../types/serviceJob.types';

const BASE = '/api/v1/complaints-management';

export type ServiceJobsListParams = DataGridApiFetchParams & {
  status?: string[];
  technician_id?: string[];
  date_from?: string;
  date_to?: string;
};

export function serviceJobListExtraParams(params: ServiceJobsListParams) {
  return {
    status: params.status?.length ? params.status : undefined,
    technician_id: params.technician_id?.length ? params.technician_id : undefined,
    date_from: params.date_from,
    date_to: params.date_to,
  };
}

export async function getServiceJobs(
  params: ServiceJobsListParams,
): Promise<DataGridApiResponse<ServiceJob>> {
  const qs = buildDataGridParams(params, serviceJobListExtraParams(params));
  const response = await apiFetch(`${BASE}/service-jobs?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load service jobs'));
  return response.json();
}

export async function getServiceJob(id: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/service-jobs/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the service job'));
  return response.json();
}

export async function getComplaintServiceJobs(complaintId: string): Promise<ServiceJob[]> {
  const response = await apiFetch(`${BASE}/complaints/${complaintId}/service-jobs`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load service jobs'));
  const body = await response.json();
  return body.data ?? [];
}

export async function raiseServiceJob(complaintId: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/complaints/${complaintId}/service-jobs`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to raise the service job'));
  return response.json();
}

async function postJson(url: string, body: unknown, fallback: string): Promise<ServiceJob> {
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

export function confirmServiceJob(id: string, values: ConfirmJobValues) {
  return postJson(`${BASE}/service-jobs/${id}/confirm`, values, 'Failed to confirm the date');
}

export function assignServiceJob(id: string, technicianId: string) {
  return postJson(
    `${BASE}/service-jobs/${id}/assign`,
    { technician_id: technicianId },
    'Failed to assign the technician',
  );
}

export function transitionServiceJob(id: string, values: TransitionValues) {
  return postJson(`${BASE}/service-jobs/${id}/transition`, values, 'Failed to update the service job');
}

export async function getDispatchBoard(day: string): Promise<DispatchBoard> {
  const response = await apiFetch(`${BASE}/service-jobs/board?day=${encodeURIComponent(day)}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the dispatch board'));
  return response.json();
}
