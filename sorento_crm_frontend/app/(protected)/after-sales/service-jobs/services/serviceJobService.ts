import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  ConfirmJobValues,
  ServiceJobFormValues,
  ServiceJobProduct,
  ServiceJobProductValues,
  CatalogueProduct,
  DispatchBoard,
  ServiceJob,
  TransitionValues,
} from '../types/serviceJob.types';

const BASE = '/api/v1/after-sales';

export type ServiceJobsListParams = DataGridApiFetchParams & {
  status?: string[];
  technician_id?: string[];
  warranty_summary?: string[];
  date_from?: string;
  date_to?: string;
};

export function serviceJobListExtraParams(params: ServiceJobsListParams) {
  return {
    status: params.status?.length ? params.status : undefined,
    technician_id: params.technician_id?.length ? params.technician_id : undefined,
    warranty_summary: params.warranty_summary?.length ? params.warranty_summary : undefined,
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

export async function createServiceJob(values: ServiceJobFormValues): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/service-jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create the service job'));
  return response.json();
}

export async function updateServiceJob(id: string, values: ServiceJobFormValues): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/service-jobs/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the service job'));
  return response.json();
}

/**
 * Complaint numbers for the optional "Related complaint" picker: the EXISTING complaints list,
 * read-only. A caller without complaint view never reaches it (the picker is hidden).
 */
export async function searchComplaintNumbers(query: string): Promise<{ id: string; complaint_number: string }[]> {
  const qs = buildDataGridParams({
    pageIndex: 0,
    pageSize: 20,
    sorting: [{ id: 'created_at', desc: true }],
    searchQuery: query,
  });
  const response = await apiFetch(`/api/v1/complaints-management/complaints?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to search complaints'));
  const body = await response.json();
  return (body.data ?? []).filter((c: { complaint_number?: string }) => !!c.complaint_number);
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

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function getServiceJobProducts(jobId: string): Promise<ServiceJobProduct[]> {
  const response = await apiFetch(`${BASE}/service-jobs/${jobId}/products`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the products'));
  return response.json();
}

export async function addServiceJobProduct(
  jobId: string,
  values: ServiceJobProductValues,
): Promise<ServiceJobProduct> {
  const response = await apiFetch(`${BASE}/service-jobs/${jobId}/products`, jsonInit('POST', values));
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to add the product'));
  return response.json();
}

export async function updateServiceJobProduct(
  jobId: string,
  lineId: string,
  values: Partial<Omit<ServiceJobProductValues, 'product_id'>>,
): Promise<ServiceJobProduct> {
  const response = await apiFetch(
    `${BASE}/service-jobs/${jobId}/products/${lineId}`,
    jsonInit('PATCH', values),
  );
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the product'));
  return response.json();
}

export async function deleteServiceJobProduct(jobId: string, lineId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/service-jobs/${jobId}/products/${lineId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to remove the product'));
}

/** Catalogue products for the Add product picker: the existing products list, read-only. */
export async function searchCatalogueProducts(query: string): Promise<CatalogueProduct[]> {
  const qs = buildDataGridParams({
    pageIndex: 0,
    pageSize: 20,
    sorting: [{ id: 'product_code', desc: false }],
    searchQuery: query,
  });
  const response = await apiFetch(`/api/v1/master-data/products?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to search products'));
  const body = await response.json();
  return (body.data ?? []).map((p: CatalogueProduct) => ({
    id: p.id,
    product_code: p.product_code,
    product_name: p.product_name,
  }));
}

/** The defect-type options (id and label) a product line can name. */
export async function getDefectOptions(): Promise<{ id: string; label: string }[]> {
  const response = await apiFetch(`${BASE}/warranty/defect-types`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load defect types'));
  return response.json();
}
