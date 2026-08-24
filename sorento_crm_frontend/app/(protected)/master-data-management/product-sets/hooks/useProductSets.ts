import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

export function useProductSets(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [
      'product-sets',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
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
