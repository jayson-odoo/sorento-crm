import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { decodeAdvancedFilter } from '@/lib/listNavQuery';
import { getSuppliers, getSupplier, createSupplier, updateSupplier, deleteSupplier } from '../services/supplierService';
import type { Supplier, SupplierFormData } from '../types/supplier.types';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';


export type SuppliersListQueryParams = DataGridApiFetchParams & {
  country?: string;
  city?: string;
  payment_terms_days?: number;
  status?: string;
  advancedFilter?: ListQueryFilterGroup | null;
};

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function suppliersListQueryKey(params: SuppliersListQueryParams): QueryKey {
  return [
    'suppliers',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.country,
    params.city,
    params.payment_terms_days,
    params.status,
    params.advancedFilter,
  ];
}

/** One page of the suppliers list, advanced filter included. */
export function fetchSuppliersPage(
  params: SuppliersListQueryParams,
): Promise<DataGridApiResponse<Supplier>> {
  if (params.advancedFilter) {
    const sortField = params.sorting?.[0]?.id || '';
    const sortDirection = params.sorting?.[0]?.desc ? 'desc' : 'asc';
    return postListQuerySearch<Supplier>({
      resource: 'suppliers',
      filter: params.advancedFilter,
      page: params.pageIndex + 1,
      limit: params.pageSize,
      sort: sortField || 'created_at',
      dir: sortDirection,
      quick_search: params.searchQuery || undefined,
    });
  }
  return getSuppliers(params);
}

/** The list query a detail URL describes, in the shape the list passes. */
export function suppliersListParamsFromUrl(
  params: ListPagerParams,
): SuppliersListQueryParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    advancedFilter:
      decodeAdvancedFilter<ListQueryFilterGroup>(params.filters.advFilter) ?? undefined,
  };
}

/** The pager's two hooks into the suppliers list. */
export const suppliersPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    suppliersListQueryKey(suppliersListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchSuppliersPage(suppliersListParamsFromUrl(params)),
};

export function useSuppliers(params: SuppliersListQueryParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: suppliersListQueryKey(params),
    queryFn: () => fetchSuppliersPage(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useSupplier(id: string | null) {
  return useQuery({
    queryKey: ['supplier', id],
    queryFn: () => {
      if (!id) throw new Error('Supplier ID is required');
      return getSupplier(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SupplierFormData) => createSupplier(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
      toast.success('Supplier created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create supplier'),
  });
}

export function useUpdateSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<SupplierFormData> }) => updateSupplier(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
      queryClient.invalidateQueries({ queryKey: ['supplier'] });
      toast.success('Supplier updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update supplier'),
  });
}

export function useDeleteSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSupplier(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
      toast.success('Supplier deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete supplier'),
  });
}
