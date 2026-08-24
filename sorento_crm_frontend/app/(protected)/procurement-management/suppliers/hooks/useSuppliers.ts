import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  getSuppliers,
  getSupplier,
  createSupplier,
  updateSupplier,
  deleteSupplier,
  SUPPLIER_NEIGHBOURS_PATH,
  type SuppliersListParams,
} from '../services/supplierService';
import type { Supplier, SupplierFormData } from '../types/supplier.types';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

/**
 * Prev/next neighbours of a supplier within the active filtered+sorted list set.
 * Serializes the list query (search/sort) with `buildDataGridParams` - the same
 * serialization the list page uses - so the backend honours the filter/sort
 * identically. `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useSupplierNeighbours(
  supplierId: string | null,
  listParams: SuppliersListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams);
  return useRecordNeighbours(SUPPLIER_NEIGHBOURS_PATH, supplierId, params);
}

export function useSuppliers(
  params: DataGridApiFetchParams & {
    country?: string;
    city?: string;
    payment_terms_days?: number;
    status?: string;
    advancedFilter?: ListQueryFilterGroup | null;
  },
) {
  return useQuery({
    queryKey: [
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
    ],
    queryFn: async () => {
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
    },
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
