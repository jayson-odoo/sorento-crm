import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  createProductSet,
  deleteProductSet,
  getProductSet,
  getProductSets,
  updateProductSet,
} from '../services/productSetService';
import type { ProductSetPayload } from '../types/productSet.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function productSetsListQueryKey(params: DataGridApiFetchParams): QueryKey {
  return [
    'product-sets',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function productSetsListParamsFromUrl(params: ListPagerParams): DataGridApiFetchParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
  };
}

/** The pager's two hooks into the product sets list. */
export const productSetsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    productSetsListQueryKey(productSetsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getProductSets(productSetsListParamsFromUrl(params)),
};

export function useProductSets(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: productSetsListQueryKey(params),
    queryFn: () => getProductSets(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useProductSet(id: string | null) {
  return useQuery({
    queryKey: ['product-set', id],
    queryFn: () => {
      if (!id) throw new Error('Product set ID is required');
      return getProductSet(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateProductSet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductSetPayload) => createProductSet(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-sets'] });
      toast.success('Product set created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create product set'),
  });
}

export function useUpdateProductSet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductSetPayload }) =>
      updateProductSet(id, data),
    onSuccess: (_res, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['product-sets'] });
      queryClient.invalidateQueries({ queryKey: ['product-set', id] });
      toast.success('Product set updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save product set'),
  });
}

export function useDeleteProductSet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProductSet(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-sets'] });
      toast.success('Product set deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete product set'),
  });
}
