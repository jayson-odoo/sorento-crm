import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { MasterQuotationTableRow } from '../types/quotationList.types';
import { fetchMasterQuotationsTable } from '../services/quotationsListService';

type Params = DataGridApiFetchParams & {
  owner_user_id?: string;
  quotation_stage_code?: string;
  scope?: 'mine' | 'all';
};

export function useQuotationsList(
  params: Params,
  options?: Pick<UseQueryOptions<DataGridApiResponse<MasterQuotationTableRow>>, 'enabled'>,
) {
  return useQuery({
    queryKey: [
      'commercial-master-quotations-table',
      params.pageIndex,
      params.pageSize,
      params.searchQuery,
      params.owner_user_id,
      params.quotation_stage_code,
      params.scope,
    ],
    queryFn: () => fetchMasterQuotationsTable(params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: options?.enabled ?? true,
  });
}
