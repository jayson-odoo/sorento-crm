import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { Branch } from '../types/branch.types';

export type BranchesListParams = DataGridApiFetchParams & {
  book?: string;
  /** `'yes'` / `'no'`: whether the branch's AccNo matches a CRM customer. */
  inCrm?: 'yes' | 'no';
  customerId?: string;
};

export async function getBranches(params: BranchesListParams): Promise<DataGridApiResponse<Branch>> {
  const qs = buildDataGridParams(params, {
    book: params.book,
    in_crm: params.inCrm === undefined ? undefined : params.inCrm === 'yes',
    customer_id: params.customerId,
  });
  const response = await apiFetch(`/api/v1/order-management/branches?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch branches'));
  return response.json();
}

export async function getBranchBooks(): Promise<string[]> {
  const response = await apiFetch('/api/v1/order-management/branches/books');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch books'));
  return response.json();
}
