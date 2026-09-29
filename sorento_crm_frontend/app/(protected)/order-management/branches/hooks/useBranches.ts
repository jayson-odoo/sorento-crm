import { useQuery } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { getBranchBooks, getBranches, type BranchesListParams } from '../services/branchService';

export function useBranches(params: BranchesListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'branches',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.book,
      params.inCrm,
      params.customerId,
    ],
    queryFn: () => getBranches(params),
  });
}

export function useBranchBooks() {
  return useQuery({
    queryKey: ['branch-books'],
    queryFn: getBranchBooks,
    staleTime: 1000 * 60 * 10,
  });
}
