import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getBrands, getBrand, createBrand, updateBrand } from '../services/brandService';
import type { BrandFormData } from '../types/brand.types';

export function useBrands(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: ['brands', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getBrands(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useBrand(id: string | null) {
  return useQuery({
    queryKey: ['brand', id],
    queryFn: () => {
      if (!id) throw new Error('Brand ID is required');
      return getBrand(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateBrand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BrandFormData) => createBrand(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-select'] });
      toast.success('Brand created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create brand'),
  });
}

export function useUpdateBrand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<BrandFormData> }) => updateBrand(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand'] });
      queryClient.invalidateQueries({ queryKey: ['brand-select'] });
      toast.success('Brand updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update brand'),
  });
}

