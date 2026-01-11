import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getSuppliers, getSupplier, createSupplier, updateSupplier, deleteSupplier } from '../services/supplierService';
import type { SupplierFormData } from '../types/supplier.types';

export function useSuppliers(params: DataGridApiFetchParams & { country?: string; city?: string; payment_terms_days?: number; status?: string }) {
  return useQuery({
    queryKey: ['suppliers', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.country, params.city, params.payment_terms_days, params.status],
    queryFn: () => getSuppliers(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
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
