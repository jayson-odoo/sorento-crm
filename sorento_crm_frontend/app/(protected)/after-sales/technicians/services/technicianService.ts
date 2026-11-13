import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { Technician, TechnicianFormValues } from '../types/technician.types';

const BASE = '/api/v1/after-sales/technicians';

export type TechniciansListParams = DataGridApiFetchParams & {
  employment_type?: string[];
  is_active?: string[];
};

export async function getTechnicians(
  params: TechniciansListParams,
): Promise<DataGridApiResponse<Technician>> {
  const qs = buildDataGridParams(params, {
    employment_type: params.employment_type?.length ? params.employment_type : undefined,
    is_active: params.is_active?.length ? params.is_active : undefined,
  });
  const response = await apiFetch(`${BASE}?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load technicians'));
  return response.json();
}

/** Active technicians for the Assign picker and the list filter. */
export async function getTechniciansSelect(): Promise<Technician[]> {
  const qs = buildDataGridParams(
    { pageIndex: 0, pageSize: 200, sorting: [{ id: 'name', desc: false }], searchQuery: '' },
    { is_active: ['true'] },
  );
  const response = await apiFetch(`${BASE}?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load technicians'));
  const body = await response.json();
  return body.data ?? [];
}

export async function createTechnician(values: TechnicianFormValues): Promise<Technician> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create the technician'));
  return response.json();
}

export async function updateTechnician(
  id: string,
  values: Partial<TechnicianFormValues> & { is_active?: boolean },
): Promise<Technician> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the technician'));
  return response.json();
}

export async function deleteTechnician(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the technician'));
}
