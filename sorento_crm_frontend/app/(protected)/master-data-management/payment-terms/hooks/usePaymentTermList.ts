import { useQuery } from '@tanstack/react-query';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { getPaymentTermList } from '../services/paymentTermListService';

export function usePaymentTermList(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['payment-terms', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getPaymentTermList(params),
    retry: 1,
  });
}
