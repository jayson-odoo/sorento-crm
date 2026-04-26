import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { MasterQuotationTableRow } from '../types/quotationList.types';

const CM = '/api/commercial-management';

export async function fetchMasterQuotationsTable(
  params: DataGridApiFetchParams & {
    owner_user_id?: string;
    quotation_stage_code?: string;
    scope?: 'mine' | 'all';
  },
): Promise<DataGridApiResponse<MasterQuotationTableRow>> {
  const { pageIndex, pageSize, searchQuery, owner_user_id, quotation_stage_code, scope } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    scope: scope ?? 'all',
    ...(searchQuery?.trim() ? { search: searchQuery.trim() } : {}),
    ...(owner_user_id ? { owner_user_id } : {}),
    ...(quotation_stage_code && quotation_stage_code !== '__all__'
      ? { quotation_stage_code }
      : {}),
  });
  const response = await apiFetch(`${CM}/master-quotations?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch quotations');
  return response.json();
}
